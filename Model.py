# Load a local copy of the current ODYM branch:
import sys
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pickle
from seaborn.palettes import color_palette
import xlrd
import pylab
from copy import deepcopy
import logging as log
import xlwt
import tqdm
import math
from scipy.stats import norm
from tqdm import tqdm
import time
import matplotlib
import product_component_model as pcm
mpl_logger = log.getLogger("matplotlib")
mpl_logger.setLevel(log.WARNING)  
# For Ipython Notebook only
### Preamble

# add ODYM module directory to system path, relative
MainPath = os.path.join(os.getcwd(), 'odym', 'modules')
sys.path.insert(0, MainPath)

# add ODYM module directory to system path, absolute
sys.path.insert(0, os.path.join(os.getcwd(), 'odym', 'modules'))

# Specify path to dynamic stock model and to datafile, relative
DataPath = os.path.join( 'docs', 'files')

# Specify path to dynamic stock model and to datafile, absolute
DataPath = os.path.join(os.getcwd(), 'docs', 'Files')

import ODYM_Classes as msc # import the ODYM class file
import ODYM_Functions as msf # import the ODYM function file
import dynamic_stock_model as dsm # import the dynamic stock model library

# Initialize loggin routine
log_verbosity = eval("log.DEBUG")
log_filename = 'LogFileTest.md'
[Mylog, console_log, file_log] = msf.function_logger(log_filename, os.getcwd(),
                                                     log_verbosity, log_verbosity)
Mylog.info('### 1. - Initialize.')

#Read main script parameters
#Load project-specific config file
ProjectSpecs_ConFile = 'ODYM_Config_Vehicle_System.xlsx'
Model_Configfile     = xlrd.open_workbook(os.path.join(DataPath, ProjectSpecs_ConFile))
ScriptConfig         = {'Model Setting': Model_Configfile.sheet_by_name('Config').cell_value(3,3)} # Dictionary with config parameters
Model_Configsheet    = Model_Configfile.sheet_by_name('Setting_' + ScriptConfig['Model Setting'])

Name_Scenario        = Model_Configsheet.cell_value(3,3)
print(Name_Scenario)

#Read control and selection parameters into dictionary
ScriptConfig         = msf.ParseModelControl(Model_Configsheet,ScriptConfig)

Mylog.info('Read and parse config table, including the model index table, from model config sheet.')
IT_Aspects,IT_Description,IT_Dimension,IT_Classification,IT_Selector,IT_IndexLetter,\
PL_Names,PL_Description,PL_Version,PL_IndexStructure,PL_IndexMatch,PL_IndexLayer,\
PrL_Number,PrL_Name,PrL_Comment,PrL_Type,ScriptConfig = msf.ParseConfigFile(Model_Configsheet,ScriptConfig,Mylog)    

class_filename       = 'ODYM_Classifications_Master_Vehicle_System.xlsx'
Classfile            = xlrd.open_workbook(os.path.join(DataPath,class_filename))
Classsheet           = Classfile.sheet_by_name('MAIN_Table')
MasterClassification = msf.ParseClassificationFile_Main(Classsheet,Mylog)


Mylog.info('Define model classifications and select items for model classifications according to information provided by config file.')
ModelClassification  = {} # Dict of model classifications
for m in range(0,len(IT_Aspects)):
    ModelClassification[IT_Aspects[m]] = deepcopy(MasterClassification[IT_Classification[m]])
    EvalString = msf.EvalItemSelectString(IT_Selector[m],len(ModelClassification[IT_Aspects[m]].Items))
    if EvalString.find(':') > -1: # range of items is taken
        RangeStart = int(EvalString[0:EvalString.find(':')])
        RangeStop  = int(EvalString[EvalString.find(':')+1::])
        ModelClassification[IT_Aspects[m]].Items = ModelClassification[IT_Aspects[m]].Items[RangeStart:RangeStop]           
    elif EvalString.find('[') > -1: # selected items are taken
        ModelClassification[IT_Aspects[m]].Items = [ModelClassification[IT_Aspects[m]].Items[i] for i in eval(EvalString)]
    elif EvalString == 'all':
        None
    else:
        Mylog.error('Item select error for aspect ' + IT_Aspects[m] + ' were found in datafile.')
        break

# Define model index table and parameter dictionary
Mylog.info('### 2.2 - Define model index table and parameter dictionary')
Model_Time_Start = int(min(ModelClassification['Time'].Items))
Model_Time_End   = int(max(ModelClassification['Time'].Items))
Model_Duration   = Model_Time_End - Model_Time_Start + 1

Mylog.info('Define index table dataframe.')
IndexTable = pd.DataFrame({'Aspect'        : IT_Aspects,  # 'Time' and 'Element' must be present!
                           'Description'   : IT_Description,
                           'Dimension'     : IT_Dimension,
                           'Classification': [ModelClassification[Aspect] for Aspect in IT_Aspects],
                           'IndexLetter'   : IT_IndexLetter})  # Unique one letter (upper or lower case) indices to be used later for calculations.

# Default indexing of IndexTable, other indices are produced on the fly
IndexTable.set_index('Aspect', inplace=True)

# Add indexSize to IndexTable:
IndexTable['IndexSize'] = pd.Series([len(IndexTable.Classification[i].Items) for i in range(0, len(IndexTable.IndexLetter))],
                                    index=IndexTable.index)

# list of the classifications used for each indexletter
IndexTable_ClassificationNames = [IndexTable.Classification[i].Name for i in range(0, len(IndexTable.IndexLetter))]


# Define dimension sizes
Nt = len(IndexTable.Classification[IndexTable.index.get_loc('Time')].Items)
Nc = len(IndexTable.Classification[IndexTable.index.get_loc('Age-cohort')].Items)
Ng = len(IndexTable.Classification[IndexTable.index.get_loc('Drive_train')].Items)
Ne = len(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items)
Nb = len(IndexTable.Classification[IndexTable.index.get_loc('Battery_Chemistry')].Items)
Ns = len(IndexTable.Classification[IndexTable.index.get_loc('Size')].Items)
Nh = len(IndexTable.Classification[IndexTable.index.get_loc('Recycling_Process')].Items)
NS = len(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items)
Na = len(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items)
Nz = len(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items)
NR = len(IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items)
NE = len(IndexTable.Classification[IndexTable.index.get_loc('Energy_Storage_Scenarios')].Items)


ParameterDict = {}
mo_start = 0 # set mo for re-reading a certain parameter
ParameterDict['Vehicle_stock']= msc.Parameter(Name = 'Vehicle_stock',
                                                             ID = 1,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'z,t', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/IUS/regionalized_IUS_OICA.npy')[:,5,:], # in millions
                                                             Uncert=None,
                                                             Unit = '# passenger cars')

ParameterDict['Drive_train_shares']= msc.Parameter(Name = 'Drive_train_shares',
                                                             ID = 2,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'S,g,t', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/motorEnergy/motorEnergy_IEA.npy'), # in %
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Segment_shares']= msc.Parameter(Name = 'Segment_shares',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'S,g,s,c', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/vehicle_size/vehicleSize_motorEnergy_passengerCars.npy')[:,5,:,:,:], # in %
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Battery_chemistry_shares']= msc.Parameter(Name = 'Battery_chemistry_shares',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'a,g,b,c', #t=time, h=units
                                                             Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryChemistry/batteryChemistry_batteryScenarios.npy')[:,5,:,:,:], # in %
                                                             Uncert=None,
                                                             Unit = '%')



ParameterDict['Material_content']= msc.Parameter(Name = 'Materials',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,s,b,e', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/material_content.npy'), # in kg 
                                                             Uncert=None,
                                                             Unit = '%')

# ParameterDict['Capacity']= msc.Parameter(Name = 'Capacity',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'b,p,c', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryCapacity.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')


# ParameterDict['Degradation']= msc.Parameter(Name = 'Degradation',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'b,t,c', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryCapacity/degradation.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')

ParameterDict['Reuse_rate']= msc.Parameter(Name = 'Reuse',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'R,b,t', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/reuse_scenarios.npy'),
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Recycling_efficiency']= msc.Parameter(Name = 'Efficiency',
                                                              ID = 3,
                                                              P_Res = None,
                                                              MetaData = None,
                                                              Indices = 'e,h', #t=time, h=units
                                                              Values = np.load(os.getcwd()+'/data/scenario_data/recycling_efficiency.npy'),
                                                              Uncert=None,
                                                              Unit = '%')


# ParameterDict['Storage_demand']= msc.Parameter(Name = 'Storage_demand',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'E,t', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/energyStorage/demandStationaryStorage.npy'),
#                                                              Uncert=None,
#                                                              Unit = 'GWh')

MaTrace_System = msc.MFAsystem(Name = 'MaTrace_Vehicle_Fleet_Global', 
                      Geogr_Scope = 'EU', 
                      Unit = 'Vehicles', 
                      ProcessList = [], 
                      FlowDict = {}, 
                      StockDict = {},
                      ParameterDict = ParameterDict, 
                      Time_Start = Model_Time_Start, 
                      Time_End = Model_Time_End, 
                      IndexTable = IndexTable, 
                      Elements = IndexTable.loc['Element'].Classification.Items) # Initialize MFA system

# Add processes to system
for m in range(0, len(PrL_Number)):
    MaTrace_System.ProcessList.append(msc.Process(Name = PrL_Name[m], ID   = PrL_Number[m]))

# Define the flows of the Vehicle system, and initialise their values:
MaTrace_System.FlowDict['V_2_3'] = msc.Flow(Name = 'Vehicles flowing into the stock ', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,g,s,t', Values=None)
MaTrace_System.FlowDict['V_3_4'] = msc.Flow(Name = 'Outflows from use phase to ELV collection and dismantling', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,g,s,t,c', Values=None)
# Initialize vehicle stocks
MaTrace_System.StockDict['S_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,g,s,t', Values=None)
MaTrace_System.StockDict['S_C_3']   = msc.Stock(Name = 'xEV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,g,s,t,c', Values=None)
MaTrace_System.StockDict['dS_3']  = msc.Stock(Name = 'xEV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,g,s,t', Values=None)


# Initialize LIB layer

MaTrace_System.FlowDict['B_1_2'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_2_3'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_3_4'] = msc.Flow(Name = 'Outflows from use phase to ELV collection and dismantling', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_4_5'] = msc.Flow(Name = 'Used LIBs for health assessment and dismantling', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_5_6'] = msc.Flow(Name = 'Used LIBs as second life ', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_1_6'] = msc.Flow(Name = 'New LIBs for stationary storage ', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_5_8'] = msc.Flow(Name = 'Spent LIBs directly to recycling', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_6_7'] = msc.Flow(Name = 'Spent LIBs after second life to ELB collector', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_7_8'] = msc.Flow(Name = 'Spent LIBs after second life to to recycling', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
# Initializing stocks at transport stage
MaTrace_System.StockDict['B_3']   = msc.Stock(Name = 'LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_3']   = msc.Stock(Name = 'LIBs EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_3']  = msc.Stock(Name = 'LIBs in EV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
# Initializing stocks of SLBs at stationary storage stage
MaTrace_System.StockDict['B_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_6_SLB']  = msc.Stock(Name = 'Stock change of SLBs in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
# Initializing stocks of NSB at stationary storage stage
MaTrace_System.StockDict['B_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_6_NSB']  = msc.Stock(Name = 'Stock change of NSB in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)

# Initialize elements layer
MaTrace_System.FlowDict['E_0_1'] = msc.Flow(Name = 'Raw materials needed for batteries', P_Start = 0, P_End = 1,
                                            Indices = 'z,S,a,R,b,e,h,t', Values=None)
MaTrace_System.FlowDict['E_1_2'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,g,s,b,e,t', Values=None)
MaTrace_System.FlowDict['E_2_3'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,g,s,b,e,t', Values=None)
MaTrace_System.FlowDict['E_3_4'] = msc.Flow(Name = 'Outflows from use phase to ELV collection and dismantling', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,b,e,t', Values=None)
MaTrace_System.FlowDict['E_4_5'] = msc.Flow(Name = 'Used LIBs for health assessment and dismantling', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,b,e,t', Values=None)
MaTrace_System.FlowDict['E_5_6'] = msc.Flow(Name = 'Used LIBs as second life ', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.FlowDict['E_5_8'] = msc.Flow(Name = 'Spent LIBs directly to recycling', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.FlowDict['E_6_7'] = msc.Flow(Name = 'Spent LIBs after second life to ELB collector', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.FlowDict['E_7_8'] = msc.Flow(Name = 'Spent LIBs after second life to to recycling', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.FlowDict['E_8_1'] = msc.Flow(Name = 'Recycled materials materials for battery production', P_Start = 8, P_End = 1,
                                            Indices = 'z,S,a,R,b,e,h,t', Values=None)
# Initializing stocks at transport stage
MaTrace_System.StockDict['E_3']   = msc.Stock(Name = 'LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t', Values=None)
MaTrace_System.StockDict['E_C_3']   = msc.Stock(Name = 'LIBs EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.StockDict['dE_3']  = msc.Stock(Name = 'LIBs in EV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
# Initializing stocks of SLBs at stationary storage stage
MaTrace_System.StockDict['E_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.StockDict['E_C_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,b,e,t,c', Values=None)
MaTrace_System.StockDict['dE_6_SLB']  = msc.Stock(Name = 'Stock change of SLBs in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,R,b,e,t,c', Values=None)
# Initializing stocks of NSB at stationary storage stage
MaTrace_System.StockDict['E_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,b,e,t', Values=None)
MaTrace_System.StockDict['E_C_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,b,e,t,c', Values=None)
MaTrace_System.StockDict['dE_6_NSB']  = msc.Stock(Name = 'Stock change of NSB in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,R,g,b,e,t,c', Values=None)

# Initializing energy layer
MaTrace_System.StockDict['C_3']   = msc.Stock(Name = 'Total capacity of EV stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,t', Values=None)
MaTrace_System.StockDict['Con_3']   = msc.Stock(Name = 'Capacity of share of EV stock connected to the grid', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,t', Values=None)
MaTrace_System.StockDict['Pcon_3']   = msc.Stock(Name = 'Power of share of EV stock connected to the grid', P_Res = 3, Type = 0,
                                              Indices = 'z,S,g,t', Values=None)
MaTrace_System.StockDict['C_6_SLB']   = msc.Stock(Name = 'Capacity of SLBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,t', Values=None)
MaTrace_System.StockDict['C_6_NSB']   = msc.Stock(Name = 'Capacity of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,t', Values=None)
MaTrace_System.StockDict['Pow_3']   = msc.Stock(Name = 'Total power of EV stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,g,t', Values=None)
MaTrace_System.StockDict['Pow_6_SLB']   = msc.Stock(Name = 'Power of SLBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,t', Values=None)
MaTrace_System.StockDict['Pow_6_NSB']   = msc.Stock(Name = 'Power of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,t', Values=None)

MaTrace_System.Initialize_FlowValues()  # Assign empty arrays to flows according to dimensions.
MaTrace_System.Initialize_StockValues() # Assign empty arrays to flows according to dimensions.

### Define lifetimes to be used in the model
'''
Since we are interested in the reuse of batteries, it is important that we understand the technical
limitations of the batteries as a good themselves, rather than batteries for transport. 
The battery lifetime in our case is defined to reflect the amount of time a battery will be
technically functional, while the vehicle lifetime will relate to how long it will be used 
for transportation puropses. Thus, we can assume a lifetime of the battery that is longer than the
conventional warranty of 10 years and use a vehicle lifetime that is closer to the vehicle 
lifetimes of conventional ICEs.

We also define a delay tau_cm to define the share of batteries that can be reused. This can be 
changed depending on the conditions, but a minimum remaining lifetime of 3 years seems like a reasonable
amount of time considering that SLBs could potentially be relatively cheap since they are considered 
waste, or in some business models are actually still the property of the OEMs. 

The Model_slb module is defined here to use the battery survival function as a proxy to the share
of batteries that can be reused.
'''
lt_bat = np.array([20])
sd_bat = np.array([5])

lt_car = np.array([16])
sd_car = np.array([4])
# Define minimum amount of useful time
tau_bat = 5
# Define SLB model
Model_slb                                                       = pcm.ProductComponentModel(t = range(0,Nt),  lt_cm = {'Type': 'Normal', 'Mean': lt_bat, 'StdDev': sd_bat}, tau_cm=tau_bat)
# Compute the survival curve of the batteries with the additional lenght for the last tau years
Model_slb.compute_sf_cm_tau()

'''
I implemented now already all scenarios, but it takes about a  minute to compute. So for debugging it 
makes sense to delete the nested for loops and just use:
z = 1 # BAU stock scenario
g = 1 # BEVs
S = 1 # Sustainable development scenario
'''
print('Running model')
for z in range(Nz):
        for g in range(0,Ng):
            for S in range(NS):
                # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
                Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': lt_car, 'StdDev': lt_car }, \
                    lt_cm = {'Type': 'Normal', 'Mean': lt_bat, 'StdDev': sd_bat}, tau_cm = tau_bat)
                Model.case_3()
                # Vehicles layer
                MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:]           = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
                MaTrace_System.StockDict['S_3'].Values[z,S,g,:,:]               = np.einsum('stc->st', MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:])
                MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:,:]              = np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
                MaTrace_System.FlowDict['V_3_4'].Values[z,S,g,:,:,:]            = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))

                ###  LIBs layer, we calculate the stocks anew but this time via the battery dynamics S_C_bat
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:]       = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:] \
                    ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
                MaTrace_System.StockDict['B_3'].Values[z,S,:,g,:,:,:]           = np.einsum('asbtc->asbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:])
                # Calculating battery inflow in the vehicles
                MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,g,:,:,:]          = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:,:])
                # Calculating batteryy demand to battery manufacturer including reuse and replacements
                #       Use Model.case_3() instead. This considers two different lifetimes, but replacements and reuse are not allowed.
                #       If we keep this definition, we need to add two additional flows B_1_3 and B_4_3
                MaTrace_System.FlowDict['B_1_2'].Values[z,S,:,g,:,:,:]            = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:], \
                    np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy())))
                # Calculating the outflows based on the battery demand. Here again, this flow will be larger than the number of vehicles due to battery replacements, if allowed.
                # At the moment: LIB flows = EV flows
                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]        = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:], \
                    np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_cm.copy())))
                MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]
                '''
                We calculate the flows of batteries into reuse. Strictly speaking, only the modules are reused and the casing and other components
                go dorectly into recycling. However, since we are only interested in the materials in the battery cells, this does not play a role. 
                
                It makes sense to consider all batteries that flow out of the vehicle fleet, including the battery failures. This is because the 
                requirements for the battery to be considered "functional" are higher in transport than in stationary application, i.e. a battery
                considered failed for transport may still be fine for stationary storage. 

                The reuse parameter does not indicate the share of batteries that are reused. Rather, it is a condition to reflect decisions on which battery chemistries to 
                reuse. LFP scenario for instance will define that only LFP chemistries are considered for reuse, but the health assessment still needs to happen. 
                '''
                for t in range(Nt):
                    for c in range(t):
                        # Calculate inflows to SLB:
                        MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,g,:,:,t,c]  = np.einsum('Rb,asb->aRsb', MaTrace_System.ParameterDict['Reuse_rate'].Values[:,:,t], \
                            MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,t,c] * Model_slb.sf_cm[t+tau_bat,c]) 
                        # Calculate outflows using the battery pdf: Consider inflow of new batteries here also
                '''
                We will treat the new batteries and second life batteries as separate flows in the model, as the NBS flows are driven by the energy layer. 
                The flows of SLBs are established first in this section and NSB calculated separately below. 
                '''
                # Calculate the stock: inflow driven model
                for a in range(Na):
                    for b in range(Nb):
                        for R in range(NR):
                            for s in range(Ns):
                                for t in range(Nt):
                                    MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,a,R,g,s,b,t,0:t]         += MaTrace_System.FlowDict['B_5_6'].Values[z,S,a,R,g,s,b,t,0:t]* Model_slb.sf_cm[t,0:t]
                MaTrace_System.StockDict['B_6_SLB'].Values[z,S,:,:,g,:,:,:]             = np.einsum('aRsbtc->aRsbt', MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,:,:])
                # Calculate stock change
                # Values for first year
                MaTrace_System.StockDict['dB_6_SLB'].Values[z,S,:,:,g,:,:,0,:]          = MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,0,:]
                # All other values
                for t in range(1,Nt):    
                    MaTrace_System.StockDict['dB_6_SLB'].Values[z,S,:,:,g,:,:,t,:]      = MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,t,:] - MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,t-1,:]
                # Calculate outflows from mass balance
                MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,g,:,:,:,:]              = MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,g,:,:,:,:] - MaTrace_System.StockDict['dB_6_SLB'].Values[z,S,:,:,g,:,:,:,:]
                # Calculate amount of battery parts to recycling after reuse TODO: Add NSB flow here
                MaTrace_System.FlowDict['B_7_8'].Values[z,S,:,:,g,:,:,:,:]                      = MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,g,:,:,:,:]
                # Calculate battery parts going directly to recycling: Total outflows minus reuse
                for R in range(NR):
                    MaTrace_System.FlowDict['B_5_8'].Values[z,S,:,R,g,:,:,:,:]                  =  MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,:,:] \
                         - MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,R,g,:,:,:,:]
                
                # Elements layer: 
                '''
                Here we calculate the material flows for Ni, Co, Li, P, C, Mn, which are materials exclusively in modules.
                Since we are only interested in the cell materials, we define the material content based on the size of the battery 
                independently of whether that battery has been dismantled or not (cell material content does not change in this process).
                See material_content.ipynb for a detailed description and data for the calculations. 

                We aggregate the cohorts to have the total flows, as the cohort composition is not interesting in the 
                context of materials. 
                '''
                MaTrace_System.StockDict['E_C_3'].Values[z,S,:,g,:,:,:,:,:]     = np.einsum('sbe, asbtc->asbetc', MaTrace_System.ParameterDict['Material_content'].Values[g,:,:,:], MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:])
                MaTrace_System.StockDict['E_3'].Values[z,S,:,g,:,:,:,:]         = np.einsum('asbetc->asbet', MaTrace_System.StockDict['E_C_3'].Values[z,S,:,g,:,:,:,:,:])
                # Calculate inflows
                MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,g,:,:,:,:]        = np.einsum('sbe,asbt->asbet',MaTrace_System.ParameterDict['Material_content'].Values[g,:,:,:], MaTrace_System.FlowDict['B_1_2'].Values[z,S,:,g,:,:,:])
                MaTrace_System.FlowDict['E_2_3'].Values[z,S,:,g,:,:,:,:]        = MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,g,:,:,:,:]
                # Calculate outflows
                MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,:,:,:]        = np.einsum('gsbe,agsbtc->abet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,:,:,:,:,:])
                MaTrace_System.FlowDict['E_4_5'].Values[z,S,:,:,:,:]        = MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,:,:,:]
                # Calculate flows at second life: Aggregate segments as no longer relevant
                MaTrace_System.FlowDict['E_5_6'].Values[z,S,:,:,:,:,:]        = np.einsum('gsbe,aRgsbtc->aRbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,:,:,:,:,:])
                MaTrace_System.FlowDict['E_6_7'].Values[z,S,:,:,:,:,:]          = np.einsum('gsbe,aRgsbtc->aRbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,:,:,:,:,:])
                # Calculate material stock? Slows down model and not necessarily insightful
                # Calculate recycling flows
                for R in range(NR):
                    MaTrace_System.FlowDict['E_5_8'].Values[z,S,:,R,:,:,:]      = MaTrace_System.FlowDict['E_4_5'].Values[z,S,:,:,:,:] - MaTrace_System.FlowDict['E_5_6'].Values[z,S,:,R,:,:,:]
                MaTrace_System.FlowDict['E_7_8'].Values[z,S,:,:,:,:,:]          = np.einsum('gsbe,aRgsbtc->aRbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_7_8'].Values[z,S,:,:,:,:,:,:,:])
                # Calculate recovered materials for different recycling technologies and corresponding promary material demand
                MaTrace_System.FlowDict['E_8_1'].Values[z,S,:,:,:,:,:,:]        = np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], MaTrace_System.FlowDict['E_7_8'].Values[z,S,:,:,:,:,:]) +\
                    np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], MaTrace_System.FlowDict['E_5_8'].Values[z,S,:,:,:,:,:])
                # Calculate demand for primary materials
                for R in range(NR):
                    for h in range(Nh):
                        MaTrace_System.FlowDict['E_0_1'].Values[z,S,:,R,:,:,h,:]    = np.einsum('agsbet->abet', MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,:,:,:,:,:]) - MaTrace_System.FlowDict['E_8_1'].Values[z,S,:,R,:,:,h,:]

'''
I suggest that for the moment, before we spend too much time visualizing the results in a fancy way,
we use the scenario_visualizations.py tool to gain an overview of the model results. We can then decide 
what is insightful and meaningful as a figure and can create those figures for the manuscript. 
'''
print('Exporting results')
# Exporting vehicle flows
results = os.path.join(os.getcwd(), 'results')
#np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/inflows/inflow_array', np.einsum('zSrgt->zSrt', MaTrace_System.FlowDict['Inflows'].Values[:,:,:,:,:]), allow_pickle=True)
np.save(results+'/arrays/vehicle_stock_array', np.einsum('zSgst->zSgt', MaTrace_System.StockDict['S_3'].Values[:,:,:,:,:]), allow_pickle=True)
np.save(results+'/arrays/vehicle_outflow_array', np.einsum('zSgstc->zSgt', MaTrace_System.FlowDict['V_3_4'].Values[:,:,:,:,:,:]), allow_pickle=True)
np.save(results+'/arrays/vehicle_inflow_array', np.einsum('zSgst->zSgt', MaTrace_System.FlowDict['V_2_3'].Values[:,:,:,:,:]), allow_pickle=True)

# Exporting battery flows
np.save(results+'/arrays/battery_inflow_array', np.einsum('zSagsbt->zSabt', MaTrace_System.FlowDict['B_2_3'].Values[:,:,:,:,:,:,:]), allow_pickle=True) 
np.save(results+'/arrays/battery_outflow_array', np.einsum('zSagsbtc->zSabt', MaTrace_System.FlowDict['B_3_4'].Values[:,:,:,:,:,:,:,:]), allow_pickle=True) 
np.save(results+'/arrays/battery_reuse_array', np.einsum('zSaRgsbtc->zSaRbt', MaTrace_System.FlowDict['B_5_6'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) 
np.save(results+'/arrays/battery_reuse_to_recycling_array',  np.einsum('zSaRgsbtc->zSaRbt',MaTrace_System.FlowDict['B_7_8'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) 
np.save(results+'/arrays/battery_recycling_array',  np.einsum('zSaRgsbtc->zSaRbt',MaTrace_System.FlowDict['B_5_8'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)
np.save(results+'/arrays/slb_stock_array', np.einsum('zSaRgsbt->zSaRbt',MaTrace_System.StockDict['B_6_SLB'].Values[:,:,:,:,:,:,:,:]), allow_pickle=True) 


# Exporting material flows
np.save(results+'/arrays/material_inflow_array',  np.einsum('zSagsbet->zSaet',MaTrace_System.FlowDict['E_1_2'].Values), allow_pickle=True) 
np.save(results+'/arrays/material_outflow_array', np.einsum('zSabet->zSaet', MaTrace_System.FlowDict['E_3_4'].Values), allow_pickle=True) 
np.save(results+'/arrays/material_reuse_array', np.einsum('zSaRbet->zSaRet', MaTrace_System.FlowDict['E_5_6'].Values), allow_pickle=True) 
np.save(results+'/arrays/material_reuse_to_recycling_array',  np.einsum('zSaRbet->zSaRet',MaTrace_System.FlowDict['E_7_8'].Values), allow_pickle=True) 
np.save(results+'/arrays/material_recycling_array',  np.einsum('zSaRbet->zSaRet' ,MaTrace_System.FlowDict['E_5_8'].Values), allow_pickle=True)
np.save(results+'/arrays/material_recycled_process_array', np.einsum('zSaRbeht->zSaReht', MaTrace_System.FlowDict['E_8_1'].Values), allow_pickle=True)


# from cycler import cycler
# import seaborn as sns
# custom_cycler = cycler(color=sns.color_palette('Paired', 20)) #'Set2', 'Paired', 'YlGnBu'
# for j, z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
#     for i, S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items):
#         ### Stock per DT
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
#                     np.einsum('gst->gt',MaTrace_System.StockDict['S_3'].Values[j,i,:,:,55::]/1000000))
#         #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Vehicle_stock'].Values[i,r,55::])
#         ax.set_ylabel('Nr. of Vehicles [billion]',fontsize =18)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(MaTrace_System.IndexTable['Classification']['Drive_train'].Items, loc='upper left',prop={'size':15})
#         ax.set_title('Stock per drive train {} scenario'.format(S), fontsize=20)
#         ax.set_xlabel('Year',fontsize =16)
#         #ax.set_ylim([0,5])
#         ax.tick_params(axis='both', which='major', labelsize=18)
#         fig.savefig(results+'/{}/{}/Stock_per_DT'.format(z,S))       

#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
#                     np.einsum('gstc->gt', MaTrace_System.FlowDict['V_3_4'].Values[j,i,:,:,55::,:]/1000)) 
#         ax.set_ylabel('Outflows [million]',fontsize =18)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(MaTrace_System.IndexTable['Classification']['Drive_train'].Items, loc='upper left',prop={'size':15})
#         ax.set_title('Vehicle outflows per drive train {} scenario'.format(S), fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         fig.savefig(results+'/{}/{}/Outflows_per_DT'.format(z,S))


#         ### Inflows per DT
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#                     np.einsum('gst->gt', MaTrace_System.FlowDict['V_2_3'].Values[j,i,:,:,55:]/1000))
#         ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(MaTrace_System.IndexTable['Classification']['Drive_train'].Items, loc='upper left',prop={'size':15})
#         ax.set_title('Inflows per drive train {} scenario'.format(S), fontsize=16)
#         ax.set_xlabel('Year',fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         fig.savefig(results+'/{}/{}/Inflows_per_DT'.format(z,S))

        

#         for a, b in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
#             ### Stock per chemistry BEV
#             fig, ax = plt.subplots(figsize=(8,7))
#             ax.set_prop_cycle(custom_cycler)
#             ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], 
#                         [np.einsum('st->t', MaTrace_System.StockDict['B_3'].Values[j,i,a,1,:,k,70:]/1000) for k in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], linewidth=0)
#             ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
#             right_side = ax.spines["right"]
#             right_side.set_visible(False)
#             top = ax.spines["top"]
#             top.set_visible(False)
#             ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[k] for k in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], loc='upper left',prop={'size':10})
#             ax.set_title('BEV stock by chemistry {} scenario'.format(b), fontsize=16)
#             ax.set_xlabel('Year',fontsize =16)
#             ax.tick_params(axis='both', which='major', labelsize=15)
#             fig.savefig(results+'/{}/{}/Stock_BEV_per_chemistry_{}_scenario'.format(z,S,b))

#             ### chemistry BEV shares
#             fig, ax = plt.subplots(figsize=(8,7))
#             ax.set_prop_cycle(custom_cycler)
#             ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], 
#                         [np.einsum('t->t', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,i,70:]) for i in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()]) # We only select the chemistries that are included in the given model run
#             ax.set_ylabel('Share [%]',fontsize =16)
#             right_side = ax.spines["right"]
#             right_side.set_visible(False)
#             top = ax.spines["top"]
#             top.set_visible(False)
#             ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[i] for i in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], loc='best',prop={'size':10})
#             ax.set_title('Chemistry shares {} scenario'.format(b), fontsize=16)
#             ax.set_xlabel('Year',fontsize =16)
#             ax.tick_params(axis='both', which='major', labelsize=15)
#             fig.savefig(results+'/{}/{}/Chemistry_shares_{}_scenario'.format(z,S,b))

#             # Inflows by chemistry
#             fig, ax = plt.subplots(figsize=(8,7))
#             ax.set_prop_cycle(custom_cycler)
#             ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], 
#                         [np.einsum('st->t', MaTrace_System.FlowDict['B_2_3'].Values[j,i,a,1,:,x,70:]) for x in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()]) # We only select the chemistries that are included in the given model run
#             ax.set_ylabel('BEV inflows',fontsize =16)
#             right_side = ax.spines["right"]
#             right_side.set_visible(False)
#             top = ax.spines["top"]
#             top.set_visible(False)
#             ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[i] for i in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], loc='best',prop={'size':10})
#             ax.set_title('BEV inflows {} {} {}'.format(z,S,b), fontsize=16)
#             ax.set_xlabel('Year',fontsize =16)
#             ax.tick_params(axis='both', which='major', labelsize=15)
#             fig.savefig(results+'/{}/{}/BEV_inflows_{}_scenario'.format(z,S,b))

#             ### Material demand
#             fig, ax = plt.subplots(figsize=(8,7))
#             ax.set_prop_cycle(custom_cycler)
#             ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#                         np.einsum('sbet->et',MaTrace_System.FlowDict['E_1_2'].Values[j,i,a,1,:,:,:,55:]))
#             ax.set_ylabel('Amount of materials',fontsize =16)
#             right_side = ax.spines["right"]
#             right_side.set_visible(False)
#             top = ax.spines["top"]
#             top.set_visible(False)
#             ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
#             ax.set_title('Total material demand {} {} {}'.format(z,S,b), fontsize=16)
#             ax.set_xlabel('Year',fontsize =16)
#             ax.tick_params(axis='both', which='major', labelsize=15)
#             fig.savefig(results+'/{}/{}/Material_demand_{}'.format(z,S, b))
#             for R, r in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items):
#                 ### Batteries going to SLB
#                 fig, ax = plt.subplots(figsize=(8,7))
#                 ax.set_prop_cycle(custom_cycler)
#                 ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#                             np.einsum('bet->et',MaTrace_System.FlowDict['E_8_1'].Values[j,i,a,R,:,:,0,55:]))
#                 ax.set_ylabel('Amount of materials',fontsize =16)
#                 right_side = ax.spines["right"]
#                 right_side.set_visible(False)
#                 top = ax.spines["top"]
#                 top.set_visible(False)
#                 ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
#                 ax.set_title('Recycled materials no reuse {} {} {}'.format(z,S,b), fontsize=16)
#                 ax.set_xlabel('Year',fontsize =16)
#                 ax.tick_params(axis='both', which='major', labelsize=15)
#                 fig.savefig(results+'/{}/{}/Recovered_materials_{}_{}'.format(z,S, b,r))

#                 ### Batteries going to reuse
#                 fig, ax = plt.subplots(figsize=(8,7))
#                 ax.set_prop_cycle(custom_cycler)
#                 ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#                             np.einsum('sbtc->bt',MaTrace_System.FlowDict['B_5_6'].Values[j,i,a,R,1,:,:,55:,:]))
#                 ax.set_ylabel('Amount of materials',fontsize =16)
#                 right_side = ax.spines["right"]
#                 right_side.set_visible(False)
#                 top = ax.spines["top"]
#                 top.set_visible(False)
#                 ax.legend(MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items, loc='upper left',prop={'size':15})
#                 ax.set_title('Reused batteries {} {} {}'.format(z,S,b), fontsize=16)
#                 ax.set_xlabel('Year',fontsize =16)
#                 ax.tick_params(axis='both', which='major', labelsize=15)
#                 fig.savefig(results+'/{}/{}/Reused_batteries_{}_{}'.format(z,S, b,r))

#                 ### Spent LIBs
#                 fig, ax = plt.subplots(figsize=(8,7))
#                 ax.set_prop_cycle(custom_cycler)
#                 ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#                             np.einsum('sbtc->bt',MaTrace_System.FlowDict['B_6_7'].Values[j,i,a,R,1,:,:,55:,:]))
#                 ax.set_ylabel('Amount of materials',fontsize =16)
#                 right_side = ax.spines["right"]
#                 right_side.set_visible(False)
#                 top = ax.spines["top"]
#                 top.set_visible(False)
#                 ax.legend(MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items, loc='upper left',prop={'size':15})
#                 ax.set_title('Recycled materials {} {} {}'.format(z,S,b), fontsize=16)
#                 ax.set_xlabel('Year',fontsize =16)
#                 ax.tick_params(axis='both', which='major', labelsize=15)
#                 fig.savefig(results+'/{}/{}/Spent_LIBs{}_{}'.format(z,S, b,r))

#                 ### SLB stock
#                 fig, ax = plt.subplots(figsize=(8,7))
#                 ax.set_prop_cycle(custom_cycler)
#                 ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#                             np.einsum('sbt->bt',MaTrace_System.StockDict['B_6_SLB'].Values[j,i,a,R,1,:,:,55:]))
#                 ax.set_ylabel('Amount of materials',fontsize =16)
#                 right_side = ax.spines["right"]
#                 right_side.set_visible(False)
#                 top = ax.spines["top"]
#                 top.set_visible(False)
#                 ax.legend(MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items, loc='upper left',prop={'size':15})
#                 ax.set_title('SLB stock {} {} {}'.format(z,S,b), fontsize=16)
#                 ax.set_xlabel('Year',fontsize =16)
#                 ax.tick_params(axis='both', which='major', labelsize=15)
#                 fig.savefig(results+'/{}/{}/SLB_stock_{}_{}'.format(z,S, b,r))



# # Inflows & Outflows range
# fig, ax = plt.subplots(figsize=(8,7))
# ax.set_prop_cycle(custom_cycler)
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[0,0,1,:,55:]/1000), 'y--', label='Low STEP')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[1,0,1,:,55:]/1000), 'yx', label='Medium STEP')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[2,0,1,:,55:]/1000), 'y.', label='High STEP')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[0,1,1,:,55:]/1000), 'b--', label='Low SD')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[1,1,1,:,55:]/1000), 'bx', label='Medium SD')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[2,1,1,:,55:]/1000), 'b.', label='High SD')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[0,2,1,:,55:]/1000), 'r--', label='Low Net Zero')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[1,2,1,:,55:]/1000), 'rx', label='Medium Net Zero')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[2,2,1,:,55:]/1000), 'r.', label='High Net Zero')
# ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
# right_side = ax.spines["right"]
# right_side.set_visible(False)
# top = ax.spines["top"]
# top.set_visible(False)
# ax.legend(loc='upper left',prop={'size':16})
# ax.set_title('Yearly new vehicle registrations', fontsize=16)
# ax.set_xlabel('Year',fontsize =16)
# ax.tick_params(axis='both', which='major', labelsize=15)
# ax.set_ylim([0,125])
# fig.savefig(results+'/overview/Inflows_range')

# fig, ax = plt.subplots(figsize=(8,7))
# ax.set_prop_cycle(custom_cycler)
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[0,0,1,:,55:,:]/1000), 'y--', label='Low STEP')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[2,0,1,:,55:,:]/1000), 'y.', label='High STEP')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[1,0,1,:,55:,:]/1000), 'yx', label='Medium STEP')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[0,1,1,:,55:,:]/1000), 'b--', label='Low SD')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[1,1,1,:,55:,:]/1000), 'bx', label='Medium SD')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[2,1,1,:,55:,:]/1000), 'b.', label='High SD')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[0,2,1,:,55:,:]/1000), 'r--', label='Low Net Zero')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[1,2,1,:,55:,:]/1000), 'rx', label='Medium Net Zero')
# ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
#             np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[2,2,1,:,55:,:]/1000), 'r.', label='High Net Zero')
# ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
# right_side = ax.spines["right"]
# right_side.set_visible(False)
# top = ax.spines["top"]
# top.set_visible(False)
# ax.legend(loc='upper left',prop={'size':16})
# ax.set_title('Yearly vehicle outflows', fontsize=16)
# ax.set_xlabel('Year',fontsize =16)
# ax.tick_params(axis='both', which='major', labelsize=15)
# ax.set_ylim([0,125])
# fig.savefig(results+'/overview/Outflows_range')