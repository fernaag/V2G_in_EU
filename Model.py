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



# ParameterDict['Materials']= msc.Parameter(Name = 'Materials',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'g,b,p,e', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/materialContent/matContent_motorEnergy_vehicleSize_batteryChemistry.npy'), # in kg 
#                                                              Uncert=None,
#                                                              Unit = '%')

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

# ParameterDict['Battery_Weight']= msc.Parameter(Name = 'Battery_Weight',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'g,s,b', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/batteryWeight/batteryWeight_motorEnergy_segment_batteryChemistry.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')

# ParameterDict['Battery_Parts']= msc.Parameter(Name = 'Parts',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'g,s,b,p', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/norwegian_model/batteryParts/batteryParts_motorEnergy_batteryChemistry.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')

# ParameterDict['Recycling_rate']= msc.Parameter(Name = 'Recycling',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'R,b,p,h,t', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/recyclingRate/recycingRate_batteryChemistry_batteryPart_recyclingProcess_reuseScenario.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')

# ParameterDict['SLB_recycling_rate']= msc.Parameter(Name = 'SLB Recycling',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'r,b,h,t', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/recyclingRate/recyclingRateSLB_region_chemistry_recyclingProcess.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')

# ParameterDict['Recycling_efficiency']= msc.Parameter(Name = 'Efficiency',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 'e,h', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/recycling_efficiencies/recyclingEfficiency_recyclingProcess.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')

# ParameterDict['Daily_availability']= msc.Parameter(Name = 'Daily_availability',
#                                                              ID = 3,
#                                                              P_Res = None,
#                                                              MetaData = None,
#                                                              Indices = 's,d', #t=time, h=units
#                                                              Values = np.load('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/vehicleAvailability/vehicle_availability.npy'),
#                                                              Uncert=None,
#                                                              Unit = '%')

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
                                            Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_5_8'] = msc.Flow(Name = 'Spent LIBs directly to recycling', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_6_7'] = msc.Flow(Name = 'Spent LIBs after second life to ELB collector', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_7_8'] = msc.Flow(Name = 'Spent LIBs after second life to to recycling', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,g,s,b,t,c', Values=None)
# Initializing stocks at transport stage
MaTrace_System.StockDict['B_3']   = msc.Stock(Name = 'LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_3']   = msc.Stock(Name = 'LIBs EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_3']  = msc.Stock(Name = 'LIBs in EV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
# Initializing stocks of SLBs at stationary storage stage
MaTrace_System.StockDict['B_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_6_SLB']  = msc.Stock(Name = 'Stock change of SLBs in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
# Initializing stocks of NSB at stationary storage stage
MaTrace_System.StockDict['B_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_6_NSB']  = msc.Stock(Name = 'Stock change of NSB in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)

# Initialize elements layer
MaTrace_System.FlowDict['E_0_1'] = msc.Flow(Name = 'Raw materials needed for batteries', P_Start = 0, P_End = 1,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_1_2'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_2_3'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_3_4'] = msc.Flow(Name = 'Outflows from use phase to ELV collection and dismantling', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_4_5'] = msc.Flow(Name = 'Used LIBs for health assessment and dismantling', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_5_6'] = msc.Flow(Name = 'Used LIBs as second life ', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_5_8'] = msc.Flow(Name = 'Spent LIBs directly to recycling', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_6_7'] = msc.Flow(Name = 'Spent LIBs after second life to ELB collector', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_7_8'] = msc.Flow(Name = 'Spent LIBs after second life to to recycling', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.FlowDict['E_8_1'] = msc.Flow(Name = 'Recycled materials materials for battery production', P_Start = 8, P_End = 1,
                                            Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
# Initializing stocks at transport stage
MaTrace_System.StockDict['E_3']   = msc.Stock(Name = 'LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t', Values=None)
MaTrace_System.StockDict['E_C_3']   = msc.Stock(Name = 'LIBs EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.StockDict['dE_3']  = msc.Stock(Name = 'LIBs in EV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
# Initializing stocks of SLBs at stationary storage stage
MaTrace_System.StockDict['E_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t', Values=None)
MaTrace_System.StockDict['E_C_6_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.StockDict['dE_6_SLB']  = msc.Stock(Name = 'Stock change of SLBs in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
# Initializing stocks of NSB at stationary storage stage
MaTrace_System.StockDict['E_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t', Values=None)
MaTrace_System.StockDict['E_C_6_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)
MaTrace_System.StockDict['dE_6_NSB']  = msc.Stock(Name = 'Stock change of NSB in stationary storage', P_Res = 6, Type = 1,
                                              Indices = 'z,S,a,g,s,b,e,t,c', Values=None)

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


for z in range(Nz):
        for g in range(0,Ng):
            for S in range(NS):
                # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
                Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4]) }, \
                    lt_cm = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4])}, tau_cm = 3, tau_pr=3)
                S_C_car, S_C_bat, I_car, I_bat, O_C_car, O_C_bat                = Model.case_6()
                # Vehicles layer
                MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:]           = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],S_C_car.copy()))
                MaTrace_System.StockDict['S_3'].Values[z,S,g,:,:]               = np.einsum('stc->st', MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:])
                MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:]                = np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],I_car.copy()))
                MaTrace_System.FlowDict['V_3_4'].Values[z,S,g,:,:,:]            = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , O_C_car.copy()))

                # LIBs layer, we calculate the stocks anew but this time via the battery dynamics S_C_bat
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:]       = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:] \
                    ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],S_C_bat.copy())))
                MaTrace_System.StockDict['B_3'].Values[z,S,:,g,:,:,:]           = np.einsum('asbtc->asbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:])
                # Calculating battery inflow in the vehicles
                MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,g,:,:,:]          = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:,:])
                # Calculating batteryy demand to battery manufacturer including reuse and replacements
                # TODO: Since battery replacements and reuse are allowed, this flow will be larger than the amount of vehicles entering the fleet. 
                #       If we keep this definition, we need to add two additional flows B_1_3 and B_4_3
                # FIXME: At the moment this process is not mass balanced due to the issue stated above. To change this without adjusting the system, 
                #        use Model.case_3() instead. This considers two different lifetimes, but replacements and reuse are not allowed.
                MaTrace_System.FlowDict['B_1_2'].Values[z,S,:,g,:]            = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:], \
                    np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],I_bat.copy())))
                # Calculating the outflows based on the battery demand. Here again, this flow will be larger than the number of vehicles due to battery replacements
                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]        = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:], \
                    np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , O_C_bat.copy())))
                MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]
                
                # Elements layer: This layer needs to be re-done completely, as the logic differs from my previous approach
               

# # Calculating capacities
# MaTrace_System.StockDict['C_3'].Values[:,:,:,:,:]  = np.einsum('btc,zSagsbtc->zSagt', MaTrace_System.ParameterDict['Degradation'].Values[:,:,:], np.einsum('zSagsbptc, bpc->zSagsbptc', MaTrace_System.StockDict['B_C_3'].Values[:,:,:,r,:,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]))
# #MaTrace_System.StockDict['C_6'].Values[:,:,:,:,:]  = np.einsum('btc, zSaRbtc->zSaRt', MaTrace_System.ParameterDict['Degradation'].Values[:,:,:], np.einsum('zSaRbptc, bpc->zSaRbptc', MaTrace_System.StockDict['B_C_6'].Values[:,:,:,:,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]))  #= msc.Stock(Name = 'xEV in-use stock', P_Res = 6, Type = 0,



# ### To calculate power, we multiply the number of vehicles by 7kW. For SLB, we assume that 100kWh of batteries can have a 10kW power output. 
# MaTrace_System.StockDict['Pow_3'].Values[:,:,:,:]  = np.einsum('zSgst->zSgt',MaTrace_System.StockDict['S_3'].Values[:,:,:,:,:])/7
# MaTrace_System.StockDict['Pow_6'].Values[:,:,:,:]  = MaTrace_System.StockDict['C_6'].Values[:,:,:,:,:] / 6 
# ### Calculating the real availability of vehicles
# #MaTrace_System.StockDict['Con_3'].Values[:,:,:,:,:,:] = np.einsum('zSagt, s->zSagdt',MaTrace_System.StockDict['C_3'].Values[:,:,:,r,:,:], MaTrace_System.ParameterDict['Daily_availability'].Values[:,:])
# #MaTrace_System.StockDict['Pcon_3'].Values[:,:,r,:,:,:] = np.einsum('zSgt, sd->zSgdt',MaTrace_System.StockDict['Pow_3'].Values[:,:,r,:,:], MaTrace_System.ParameterDict['Daily_availability'].Values[:,:])


# print('Solving recycling loop')

# # Solving material layer #FIXME: Add the r argument to avoid the einsum over all regions
# MaTrace_System.FlowDict['E_5_6'].Values[:,:,:,:,r,:,:,:,:]      = np.einsum('zSaRgsbptc,gbpe->zSaRbpet', MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,r,:,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:])
# MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,r,:,:,:,:,:]    = np.einsum('zSaRgsbphtc,gbpe->zSaRbpeht',MaTrace_System.FlowDict['P_5_8'].Values[:,:,:,:,r,:,:,:,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:])
# MaTrace_System.FlowDict['E_6_7'].Values[:,:,:,:,r,:,:,:] = np.einsum('zSaRbpt, gbpe->zSaRept', MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) # z,S,a,R,r,e,t
# MaTrace_System.FlowDict['P_7_8'].Values[:,:,:,:,r,:,:,:,:] = np.einsum('zSaRbpt,bht->zSaRbpht ', MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,r,:,:], MaTrace_System.ParameterDict['SLB_recycling_rate'].Values[r,:,:,:]) # FIXME: SLB recycling rate needs fixing
# MaTrace_System.FlowDict['E_7_8'].Values[:,:,:,:,r,:,:,:,:,:] = np.einsum('zSaRbpht,gbpe->zSaRbpeht ', MaTrace_System.FlowDict['P_7_8'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Materials'].Values[:,:,:,:]) # FIXME: Since the materials array is per battery, we need to change that parameter to be a fraction per battery part. Otherwise we cannot work with those values.
# MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,r,:,:,:,:] = np.einsum('eh, zSaRbpeht->zSaRpeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], (MaTrace_System.FlowDict['E_7_8'].Values[:,:,:,:,r,:,:,:,:,:] + MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,r,:,:,:,:,:]))
# MaTrace_System.FlowDict['E_8_0'].Values[:,:,:,:,r,:,:,:,:] = np.einsum('zSaRbpeht->zSaRpeht', MaTrace_System.FlowDict['E_7_8'].Values[:,:,:,:,r,:,:,:,:,:]) + np.einsum('zSaRbpeht->zSaRpeht', MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,r,:,:,:,:,:]) - MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,r,:,:,:,:]
# # Solving recycling loop

# for R in range(NR):
#     MaTrace_System.FlowDict['E_primary_Inflows'].Values[:,:,:,R,:,:,:,:] = np.einsum('zSargsbpet->zSarept', MaTrace_System.FlowDict['E_1_3'].Values[:,:,:,:,:,:,:,:,:,:]) -  np.einsum('zSarpeht->zSarept', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,R,:,:,:,:,:]) # 'z,S,a,r,g,s,b,p,e,t


# # Exporting vehicle flows
# #np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/inflows/inflow_array', np.einsum('zSrgt->zSrt', MaTrace_System.FlowDict['Inflows'].Values[:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_stock_array', np.einsum('zSrgst->zSrgt', MaTrace_System.StockDict['S_3'].Values[:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_outflow_array', np.einsum('zSrgstc->zSrgt', MaTrace_System.FlowDict['F_3_4'].Values[:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_inflow_array', np.einsum('zSrgst->zSrgt', MaTrace_System.FlowDict['F_1_3_t'].Values[:,:,:,:,:,:]), allow_pickle=True)

# # Exporting battery flows
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_inflow_array', np.einsum('zSargsbpt->zSarbpt', MaTrace_System.FlowDict['P_1_3'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,r,g,s,b,p,t
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_outflow_array', np.einsum('zSargsbpt->zSarbpt', MaTrace_System.FlowDict['P_3_4'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,r,g,s,b,p,t
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_array', np.einsum('zSaRrgsbptc->zSaRrbpt', MaTrace_System.FlowDict['P_5_6'].Values[:,:,:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,R,r,g,s,b,p,t,c
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_to_recycling_array',  MaTrace_System.FlowDict['P_6_7'].Values[:,:,:,:,:,:,:,:], allow_pickle=True) # zSaRrbpt
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_recycling_array',  np.einsum('zSaRrgsbphtc->zSaRrbpt' ,MaTrace_System.FlowDict['P_5_8'].Values[:,:,:,:,:,:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/slb_stock_array', MaTrace_System.StockDict['P_6'].Values[:,:,:,:,:,:,:,:], allow_pickle=True) # z,S,a,R,r,g,s,b,p,t,c


# # Exporting material flows
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_inflow_array',  MaTrace_System.FlowDict['E_primary_Inflows'].Values[:,:,:,:,:,:,:,:], allow_pickle=True) # zSaRrpet
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_outflow_array', np.einsum('zSargsbpet->zSarept', MaTrace_System.FlowDict['E_3_4'].Values[:,:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,r,g,s,b,p,e,t
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_array', np.einsum('zSaRrbpet->zSaRrept', MaTrace_System.FlowDict['E_5_6'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) # z,S,a,R,r,g,s,b,p,e,t,c
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_to_recycling_array',  MaTrace_System.FlowDict['E_6_7'].Values[:,:,:,:,:,:,:,:], allow_pickle=True) # zSaRrpet
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycling_array',  np.einsum('zSaRrbpeht->zSaRrept' ,MaTrace_System.FlowDict['E_5_8'].Values[:,:,:,:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycled_process_array', np.einsum('zSaRrpeht->zSaRrept', MaTrace_System.FlowDict['E_8_1'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)
# np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_losses_array', np.einsum('zSaRrpeht->zSaRrept', MaTrace_System.FlowDict['E_8_0'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)

# ### Exporting Equinor data
# np.save('/Users/fernaag/Box/BATMAN/Partners/Equinor/material_demand_NCX', np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,0,:,:,:,:,:,:,70:]/1000000)) # Demand
# np.save('/Users/fernaag/Box/BATMAN/Partners/Equinor/material_demand_LFP', np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,1,:,:,:,:,:,:,70:]/1000000)) # Demand
# np.save('/Users/fernaag/Box/BATMAN/Partners/Equinor/average_recycled_content',  (np.einsum('rpeht->et', MaTrace_System.FlowDict['E_8_1'].Values[1,1,0,1,:,:,:,:,70:])/1000000 / np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,0,:,:,:,:,:,:,70:]/1000000) + \
#         np.einsum('rpeht->et', MaTrace_System.FlowDict['E_8_1'].Values[1,1,1,1,:,:,:,:,70:]/1000000)/np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[1,1,1,:,:,:,:,:,:,70:]/1000000))/2*100) # Maximum available materials
# # Set color cycles
# #MaTrace_System.FlowDict['E_8_1'] = msc.Flow(Name = 'Secondary materials for battery produciton', P_Start = 8, P_End = 1,
# #                                            Indices = 'z,S,a,R,r,p,e,h,t', Values=None)


from cycler import cycler
import seaborn as sns
custom_cycler = cycler(color=sns.color_palette('Paired', 20)) #'Set2', 'Paired', 'YlGnBu'
results = os.path.join(os.getcwd(), 'results')
for j, z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
    for i, S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items):
        ### Stock per DT
        fig, ax = plt.subplots(figsize=(8,7))
        ax.set_prop_cycle(custom_cycler)
        ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('gst->gt',MaTrace_System.StockDict['S_3'].Values[j,i,:,:,55::]/1000000))
        #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Vehicle_stock'].Values[i,r,55::])
        ax.set_ylabel('Nr. of Vehicles [billion]',fontsize =18)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.legend(MaTrace_System.IndexTable['Classification']['Drive_train'].Items, loc='upper left',prop={'size':15})
        ax.set_title('Stock per drive train {} scenario'.format(S), fontsize=20)
        ax.set_xlabel('Year',fontsize =16)
        #ax.set_ylim([0,5])
        ax.tick_params(axis='both', which='major', labelsize=18)
        fig.savefig(results+'/{}/{}/Stock_per_DT'.format(z,S))       

        fig, ax = plt.subplots(figsize=(8,7))
        ax.set_prop_cycle(custom_cycler)
        ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('gstc->gt', MaTrace_System.FlowDict['V_3_4'].Values[j,i,:,:,55::,:]/1000)) 
        ax.set_ylabel('Outflows [million]',fontsize =18)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.legend(MaTrace_System.IndexTable['Classification']['Drive_train'].Items, loc='upper left',prop={'size':15})
        ax.set_title('Vehicle outflows per drive train {} scenario'.format(S), fontsize=20)
        ax.set_xlabel('Year',fontsize =18)
        ax.tick_params(axis='both', which='major', labelsize=15)
        fig.savefig(results+'/{}/{}/Outflows_per_DT'.format(z,S))


        ### Inflows per DT
        fig, ax = plt.subplots(figsize=(8,7))
        ax.set_prop_cycle(custom_cycler)
        ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
                    np.einsum('gst->gt', MaTrace_System.FlowDict['V_2_3'].Values[j,i,:,:,55:]/1000))
        ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.legend(MaTrace_System.IndexTable['Classification']['Drive_train'].Items, loc='upper left',prop={'size':15})
        ax.set_title('Inflows per drive train {} scenario'.format(S), fontsize=16)
        ax.set_xlabel('Year',fontsize =16)
        ax.tick_params(axis='both', which='major', labelsize=15)
        fig.savefig(results+'/{}/{}/Inflows_per_DT'.format(z,S))

        # ### SLB stock
        # for a,k in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
        #     fig, ax = plt.subplots(figsize=(8,7))
        #     ax.set_prop_cycle(custom_cycler)
        #     ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
        #                 [np.einsum('pt->t',MaTrace_System.StockDict['P_6'].Values[j,i,a,0,r,b,:,55::]/1000000) for b in np.einsum('jiaRrbpt->b', MaTrace_System.StockDict['P_6'].Values).nonzero()[0].tolist()])
        #     #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Vehicle_stock'].Values[i,r,55::]) #z,S,a,R,r,b,p,t
        #     ax.set_ylabel('Modules [kt]',fontsize =18)
        #     right_side = ax.spines["right"]
        #     right_side.set_visible(False)
        #     top = ax.spines["top"]
        #     top.set_visible(False)
        #     ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[i] for i in np.einsum('jiaRrbpt->b', MaTrace_System.StockDict['P_6'].Values).nonzero()[0].tolist()], loc='upper left',prop={'size':15})
        #     ax.set_title('SLB sotck per chemistry {} {} scenario'.format(S, k), fontsize=20)
        #     ax.set_xlabel('Year',fontsize =16)
        #     #ax.set_ylim([0,5])
        #     ax.tick_params(axis='both', which='major', labelsize=18)
        #     fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/SLB_stock_chemistry_{}'.format(z,S,k))

        # ### Stock in weight per material
        for a, b in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
        #     np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/arrays/Ni_demand_{}_scenario'.format(z,S,b), np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[j,i,a,:,:,:,:,:,:,:])/1000000)
        #     fig, ax = plt.subplots(figsize=(8,7))
        #     ax.set_prop_cycle(custom_cycler)
        #     ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
        #                 np.moveaxis(np.einsum('rgsbpet->et', MaTrace_System.StockDict['E_3'].Values[j,i,a,:,:,:,:,:,:,55:]),0,1))
        #     right_side = ax.spines["right"]
        #     right_side.set_visible(False)
        #     top = ax.spines["top"]
        #     top.set_visible(False)
        #     ax.set_ylabel('Weight [Mt]',fontsize =18)
        #     ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
        #     ax.set_title('Material stock {} scenario'.format(b), fontsize=20)
        #     ax.set_xlabel('Year',fontsize =18)
        #     ax.tick_params(axis='both', which='major', labelsize=15)
        #     fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_stock_{}_scenario'.format(z,S, b))

        #     # Material inflows
        #     fig, ax = plt.subplots(figsize=(8,7))
        #     ax.set_prop_cycle(custom_cycler)
        #     ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
        #                 np.moveaxis(np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[j,i,a,:,:,:,:,:,:,55:]/1000000), 1,0))
        #     right_side = ax.spines["right"]
        #     right_side.set_visible(False)
        #     top = ax.spines["top"]
        #     top.set_visible(False)
        #     ax.set_ylabel('Weight [Mt]',fontsize =18)
        #     ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
        #     ax.set_title('Material demand {} scenario'.format(b), fontsize=20)
        #     ax.set_xlabel('Year',fontsize =18)
        #     ax.tick_params(axis='both', which='major', labelsize=15)
        #     fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_demand_{}_scenario'.format(z,S, b))

        #     # Weight stock
        #     fig, ax = plt.subplots(figsize=(8,7))
        #     ax.set_prop_cycle(custom_cycler)
        #     ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
        #                 np.moveaxis(np.einsum('rgsbpet->et', MaTrace_System.FlowDict['E_1_3'].Values[j,i,a,:,:,:,:,:,:,55:]/1000000), 1,0))
        #     right_side = ax.spines["right"]
        #     right_side.set_visible(False)
        #     top = ax.spines["top"]
        #     top.set_visible(False)
        #     ax.set_ylabel('Weight [Mt]',fontsize =18)
        #     ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
        #     ax.set_title('Material demand {} scenario'.format(b), fontsize=20)
        #     ax.set_xlabel('Year',fontsize =18)
        #     ax.tick_params(axis='both', which='major', labelsize=15)
        #     fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_demand_{}_scenario'.format(z,S, b))

            ### Stock per chemistry BEV
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], 
                        [np.einsum('rst->t', MaTrace_System.StockDict['B_3'].Values[j,i,:,1,:,k,70:]/1000) for k in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], linewidth=0)
            ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[k] for k in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], loc='upper left',prop={'size':10})
            ax.set_title('BEV stock by chemistry {} scenario'.format(b), fontsize=16)
            ax.set_xlabel('Year',fontsize =16)
            ax.tick_params(axis='both', which='major', labelsize=15)
            fig.savefig(results+'/{}/{}/Stock_BEV_per_chemistry_{}_scenario'.format(z,S,b))

            ### chemistry BEV shares
            fig, ax = plt.subplots(figsize=(8,7))
            ax.set_prop_cycle(custom_cycler)
            ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], 
                        [np.einsum('t->t', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,i,70:]) for i in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()]) # We only select the chemistries that are included in the given model run
            ax.set_ylabel('Share [%]',fontsize =16)
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.legend([MaTrace_System.IndexTable['Classification']['Battery_Chemistry'].Items[i] for i in np.einsum('bt->b', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[a,1,:,70:]).nonzero()[0].tolist()], loc='best',prop={'size':10})
            ax.set_title('Chemistry shares {} scenario'.format(b), fontsize=16)
            ax.set_xlabel('Year',fontsize =16)
            ax.tick_params(axis='both', which='major', labelsize=15)
            fig.savefig(results+'/{}/{}/Chemistry_shares_{}_scenario'.format(z,S,b))

            
#         # Stock range
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         for e in range(Ne):
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('gsbpt->t', MaTrace_System.StockDict['E_3'].Values[j,1,0,:,:,:,:,:,e,70:]), np.einsum('rgsbpt->t', MaTrace_System.StockDict['E_3'].Values[j,1,1,:,:,:,:,:,e,70:]), alpha=0.4)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Weight [Mt]',fontsize =18)
#         ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
#         ax.set_title('Material stock {} scenario'.format(z + ' ' + S), fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_stock_range_{}_scenario'.format(z, S,z + S))
        
#         # Inflow range
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         for e in range(Ne):
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000), np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000), alpha=0.4)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Weight [Mt]',fontsize =18)
#         ax.legend(MaTrace_System.IndexTable['Classification']['Element'].Items, loc='upper left',prop={'size':15})
#         ax.set_title('Material demand {} scenario'.format(z + ' ' + S), fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_inflow_range_{}_scenario'.format(z, S,z +' '+ S))

#         # Material comparison For C, Al, Ni, Cu. Total, potential
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         material_set1 = np.array([1,2,7,8])
#         for e in material_set1:
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000), np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000), alpha=0.6)
#         ax.legend(['Graphite', 'Al', 'Ni', 'Cu'], loc='upper left',prop={'size':15})
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Weight [Mt]',fontsize =18)
#         ax.set_prop_cycle(custom_cycler)
#         for e in material_set1:
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_3_4'].Values[j,1,0,:,:,:,:,:,e,70:])/1000000, np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_3_4'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000), alpha=0.6, hatch='-')
#         ax.set_title('Secondary material vs demand {} scenario'.format(z + ' ' + S), fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_comparison_range_{}_scenario'.format(z, S,z + S))

#         # Material comparison for Li, Co, Si,  P, Mn
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         ax2 = ax.twiny()
#         material_set2 = np.array([0,3,5,6,9])
#         for i,e in enumerate(material_set2):
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000), np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000), color=plt.rcParams['axes.prop_cycle'].by_key()['color'][3+i] ,alpha=0.6)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Weight [Mt]',fontsize =18)
#         ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
#         # for i, e in enumerate(material_set2):
#         #     ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_3_4'].Values[j,1,0,:,:,:,:,:,e,70:])/1000000, np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_3_4'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000), hatch='-', color=plt.rcParams['axes.prop_cycle'].by_key()['color'][3+i], alpha=0.6)
#         ax.set_title('Secondary material vs demand {} scenario'.format(z + ' ' + S), fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Material_comparison_range_{}_scenario_set2'.format(z, S,z + S))


# ### recycled content for Li, Co, Si,  P, Mn
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         ax2 = ax.twinx()
#         ax2.set_prop_cycle(custom_cycler)
#         material_set2 = np.array([0,3,5,6])
#         for i,e in enumerate(material_set2):
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000), np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000), color=plt.rcParams['axes.prop_cycle'].by_key()['color'][3+i] ,alpha=0.6)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Weight [Mt]',fontsize =18)
#         ax2.set_ylabel('Recycled content [%]',fontsize =18)
#         #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
#         ax.set_title('Material demand and recycled content', fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax2.tick_params(axis='both', which='major', labelsize=15)
#         for i, e in enumerate(material_set2):
#             ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], (np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,0,1,:,:,e,:,70:])/1000000 / np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000) + \
#                 np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,1,:,:,e,:,70:]/1000000)/np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000))/2*100, color=plt.rcParams['axes.prop_cycle'].by_key()['color'][3+i], alpha=0.6)
#         ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
#         ax2.legend(['Rec. Li', 'Rec. Si', 'Rec. Mn', 'Rec. Co'], loc='lower right',prop={'size':15})
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Recycled_content_{}_scenario_set2'.format(z, S,z + S))

# ### recycled content for set 1

#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         ax2 = ax.twinx()
#         ax2.set_prop_cycle(custom_cycler)
#         material_set1 = np.array([1,2,7,8])
#         for i,e in enumerate(material_set1):
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000), np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000) ,alpha=0.6)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Weight [Mt]',fontsize =18)
#         ax2.set_ylabel('Recycled content [%]',fontsize =18)
#         #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
#         ax.set_title('Material demand and recycled content', fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax2.tick_params(axis='both', which='major', labelsize=15)
#         for i, e in enumerate(material_set1):
#             ax2.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], (np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,0,1,:,:,e,:,70:])/1000000 / np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000) + \
#                 np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,1,:,:,e,:,70:]/1000000)/np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000))/2*100, alpha=0.6)
#         ax.legend(['Graphite', 'Al', 'Ni', 'Cu'], loc='upper left',prop={'size':15})
#         ax2.legend(['Rec. Graphite', 'Rec. Al', 'Rec. Ni', 'Rec. Cu'], loc='lower right',prop={'size':15})
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Recycled_content_set1'.format(z, S))

#         # Sensitivity of recycled content
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         material_set3 = np.array([0,6,7])
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Recycled content [%]',fontsize =18)
#         #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
#         ax.set_title('Recycled content for NCX and LFP scenarios', fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.plot([2030, 2035], [4, 10], 'x')
#         ax.plot([2030, 2035], [12, 20], 'x')
#         ax.plot([2030, 2035], [4, 12], '*')
#         for i, e in enumerate(material_set3):
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,1,:,:,e,:,70:]/1000000)/np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000)*100, \
#                 np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,0,1,:,:,e,:,70:]/1000000)/np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,0,:,:,:,:,:,e,70:]/1000000)*100, alpha=0.6)
#         ax.legend(['Li targets', 'Co targets', 'Ni targets','Li', 'Co', 'Ni',], loc='lower right',prop={'size':15})
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Recycled_content_chemistries'.format(z, S))

#         # Sensitivity to lifetime
#         fig, ax = plt.subplots(figsize=(8,7))
#         ax.set_prop_cycle(custom_cycler)
#         material_set3 = np.array([0,6,7])
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.set_ylabel('Recycled content [%]',fontsize =18)
#         #ax.legend(['Li', 'Si', 'Mn', 'Co'], loc='upper left',prop={'size':15})
#         ax.set_title('Recycled content for different lifetimes LFP scen.', fontsize=20)
#         ax.set_xlabel('Year',fontsize =18)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.plot([2030, 2035], [4, 10], 'x')
#         ax.plot([2030, 2035], [12, 20], 'x')
#         ax.plot([2030, 2035], [4, 12], '*')
#         for i, e in enumerate(material_set3):
#             ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70:], np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,2,:,:,e,:,70:]/1000000)/np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000)*100, \
#                 np.einsum('rpht->t', MaTrace_System.FlowDict['E_8_1'].Values[j,1,1,1,:,:,e,:,70:]/1000000)/np.einsum('rgsbpt->t', MaTrace_System.FlowDict['E_1_3'].Values[j,1,1,:,:,:,:,:,e,70:]/1000000)*100, alpha=0.6)
#         ax.legend(['Li targets', 'Co targets', 'Ni targets','Li', 'Co', 'Ni',], loc='lower right',prop={'size':15})
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/{}/{}/Recycled_content_lifetime'.format(z, S))

#     ########### Energy Layer #############
#     ### Available capacity
#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Day'].Items, 
#                     MaTrace_System.StockDict['Con_3'].Values[j,i,0,r,1:,:,71]/1000000) #
#         ax.set_ylabel('Capacity [GWh]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV','HEV', 'PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Energy availability 2021'.format(b), fontsize=16)
#         ax.set_xlabel('Year', fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Energy_availability_{}_{}_scenario_2021'.format(z,S))

#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Day'].Items, 
#                     MaTrace_System.StockDict['Con_3'].Values[j,i,0,r,1:,:,100]/1000000) #
#         ax.set_ylabel('Capacity [GWh]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV', 'HEV','PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Energy availability 2050'.format(b), fontsize=16)
#         ax.set_xlabel('Year', fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Energy_availability_{}_{}_scenario_2050'.format(z,S))

#         ### Available power
#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Day'].Items, 
#                     MaTrace_System.StockDict['Pcon_3'].Values[j,i,r,1:,:,71]/1000000) #
#         ax.set_ylabel('Power Capacity [GW]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV','HEV', 'PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Power availability 2021'.format(b), fontsize=16)
#         ax.set_xlabel('Year',fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Power_availability_{}_{}_scenario_2021'.format(z,S))

#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Day'].Items, 
#                     MaTrace_System.StockDict['Pcon_3'].Values[j,i,r,1:,:,100]/1000000) #
#         ax.set_ylabel('Power Capacity [GW]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV', 'HEV', 'PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Power availability 2050'.format(b), fontsize=16)
#         ax.set_xlabel('Year',fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.show()
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Power_availability_{}_{}_scenario_2050'.format(z,S))

#         ### Maximum available capacity fleet
#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                     MaTrace_System.StockDict['C_3'].Values[j,i,0,r,1:,71:]/1000000) #
#         ax.set_ylabel('Capacity [GWh]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV', 'HEV','PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Energy availability maximum fleet'.format(b), fontsize=16)
#         ax.set_xlabel('Year', fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Energy_availability_{}_{}_scenario'.format(z,S))

#         ### Maximum available power fleet
#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                     MaTrace_System.StockDict['Pow_3'].Values[j,i,r,1:,71:]/1000000) #
#         ax.set_ylabel('Capacity [GWh]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV', 'HEV','PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Power availability maximum fleet'.format(b), fontsize=16)
#         ax.set_xlabel('Year', fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Power_availability_{}_{}_scenario'.format(z,S))

#         ### Available power SLB
#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                     MaTrace_System.StockDict['Pow_6'].Values[j,i,0,0,5,71:]/1000) #
#         ax.set_ylabel('Power Capacity [MW]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV','HEV', 'PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Power availability SLB'.format(b), fontsize=16)
#         ax.set_xlabel('Year',fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Power_availability_{}_{}_scenario_SLB'.format(z,S))

#         ### Available capacity SLB
#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                     MaTrace_System.StockDict['C_6'].Values[j,i,0,0,5,71:]/1000000) #
#         ax.set_ylabel('Energy Capacity [GW]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['BEV', 'HEV', 'PHEV'], loc='best',prop={'size':10})
#         ax.set_title('Energy availability SLB'.format(b), fontsize=16)
#         ax.set_xlabel('Year',fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         ax.tick_params(axis='x', which='major', rotation=90)
#         fig.show()
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Energy_availability_{}_{}_scenario_SLB'.format(z,S))

#         # MaTrace_System.StockDict['C_6'].Values[:,:,:,:,r,:]  = np.einsum('btc, zSaRbptc->zSaRt', MaTrace_System.ParameterDict['Degradation'].Values[:,:,:], np.einsum('zSaRbptc, bpc->zSaRbptc', MaTrace_System.StockDict['P_C_6'].Values[:,:,:,:,r,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]))  #= msc.Stock(Name = 'xEV in-use stock', P_Res = 6, Type = 0,
#         print(z, S)
# ### Available capacity SLB
#         fig, ax = plt.subplots(figsize=(12,8))
#         ax.set_prop_cycle(custom_cycler)
#         ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                             MaTrace_System.StockDict['C_6'].Values[j,i,1,0,5,71:]/1000000)  
#         ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                             MaTrace_System.StockDict['C_6'].Values[j,i,1,2,5,71:]/1000000) 
#         ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                             MaTrace_System.ParameterDict['Storage_demand'].Values[0,71:])
#         ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[71:], 
#                             MaTrace_System.ParameterDict['Storage_demand'].Values[1,71:])  
#         #ax.fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[71:],MaTrace_System.StockDict['C_6'].Values[j,i,0,2,5,71:]/1000000, MaTrace_System.ParameterDict['Storage_demand'].Values[0,71:], color='lightcoral',alpha=0.8, hatch='/')#
#         ax.set_ylabel('Energy Capacity [GWh]',fontsize =16)
#         right_side = ax.spines["right"]
#         right_side.set_visible(False)
#         top = ax.spines["top"]
#         top.set_visible(False)
#         ax.legend(['SLB from LFP scenario', 'SLB from all reused scenario','Energy storage requirements IRENA_ref', 'Energy storage requirements IRENA_remaped'], loc='best',prop={'size':10})
#         ax.set_title('Stationary energy storage needs and availability'.format(b), fontsize=16)
#         ax.set_xlabel('Year',fontsize =16)
#         ax.tick_params(axis='both', which='major', labelsize=15)
#         fig.show()
#         fig.savefig('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/Energy_Layer/Maximum_energy_storage_{}_{}_scenario'.format(z,S))

# Inflows & Outflows range
fig, ax = plt.subplots(figsize=(8,7))
ax.set_prop_cycle(custom_cycler)
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[0,0,1,:,55:]/1000), 'y--', label='Low STEP')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[1,0,1,:,55:]/1000), 'yx', label='Medium STEP')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[2,0,1,:,55:]/1000), 'y.', label='High STEP')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[0,1,1,:,55:]/1000), 'b--', label='Low SD')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[1,1,1,:,55:]/1000), 'bx', label='Medium SD')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[2,1,1,:,55:]/1000), 'b.', label='High SD')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[0,2,1,:,55:]/1000), 'r--', label='Low Net Zero')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[1,2,1,:,55:]/1000), 'rx', label='Medium Net Zero')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('st->t', MaTrace_System.FlowDict['V_2_3'].Values[2,2,1,:,55:]/1000), 'r.', label='High Net Zero')
ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
right_side = ax.spines["right"]
right_side.set_visible(False)
top = ax.spines["top"]
top.set_visible(False)
ax.legend(loc='upper left',prop={'size':16})
ax.set_title('Yearly new vehicle registrations', fontsize=16)
ax.set_xlabel('Year',fontsize =16)
ax.tick_params(axis='both', which='major', labelsize=15)
ax.set_ylim([0,125])
fig.savefig(results+'/overview/Inflows_range')

fig, ax = plt.subplots(figsize=(8,7))
ax.set_prop_cycle(custom_cycler)
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[0,0,1,:,55:,:]/1000), 'y--', label='Low STEP')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[2,0,1,:,55:,:]/1000), 'y.', label='High STEP')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[1,0,1,:,55:,:]/1000), 'yx', label='Medium STEP')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[0,1,1,:,55:,:]/1000), 'b--', label='Low SD')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[1,1,1,:,55:,:]/1000), 'bx', label='Medium SD')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[2,1,1,:,55:,:]/1000), 'b.', label='High SD')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[0,2,1,:,55:,:]/1000), 'r--', label='Low Net Zero')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[1,2,1,:,55:,:]/1000), 'rx', label='Medium Net Zero')
ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55:], 
            np.einsum('stc->t', MaTrace_System.FlowDict['V_3_4'].Values[2,2,1,:,55:,:]/1000), 'r.', label='High Net Zero')
ax.set_ylabel('Nr. of Vehicles [million]',fontsize =16)
right_side = ax.spines["right"]
right_side.set_visible(False)
top = ax.spines["top"]
top.set_visible(False)
ax.legend(loc='upper left',prop={'size':16})
ax.set_title('Yearly vehicle outflows', fontsize=16)
ax.set_xlabel('Year',fontsize =16)
ax.tick_params(axis='both', which='major', labelsize=15)
ax.set_ylim([0,125])
fig.savefig(results+'/overview/Outflows_range')