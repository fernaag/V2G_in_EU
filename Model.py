# %% 
# Load a local copy of the current ODYM branch:
from asyncio import new_event_loop
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
Nv = len(IndexTable.Classification[IndexTable.index.get_loc('V2G_Scenarios')].Items)


'''
In the following section we load the parameters. For the moment we are still working with some data of the global 
model in the following parameters: Drive_train_shares, Segment_shares, Battery_chemistry_shares. 

The rest of the parameters have either been adapted or are universally valid (material content etc.)
'''

ParameterDict = {}
mo_start = 0 # set mo for re-reading a certain parameter
ParameterDict['Vehicle_stock']= msc.Parameter(Name = 'Vehicle_stock',
                                                             ID = 1,
                                                             P_Res = 3,
                                                             MetaData = None,
                                                             Indices = 'z,t', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/stock.npy'), # in thousands
                                                             Uncert=None,
                                                             Unit = 'thousands of passenger cars')

ParameterDict['Drive_train_shares']= msc.Parameter(Name = 'Drive_train_shares',
                                                             ID = 2,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'S,g,t', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/EV_penetration.npy'), # in %
                                                             Uncert=None,
                                                             Unit = '%')
ParameterDict['Segment_shares']= msc.Parameter(Name = 'Segment_shares',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'S,g,s,c', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/vehicleSize_motorEnergy_passengerCars_global.npy')[:,5,:,:,:], # in %
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Battery_chemistry_shares']= msc.Parameter(Name = 'Battery_chemistry_shares',
                                                             ID = 4,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'a,g,b,c', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/battery_chemistries.npy')[:,:,:,:], # in %
                                                             Uncert=None,
                                                             Unit = '%')



ParameterDict['Material_content']= msc.Parameter(Name = 'Materials',
                                                             ID = 5,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,s,b,e', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/material_content.npy'), # in kg 
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Material_content_NSB']= msc.Parameter(Name = 'Materials_NSB',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,b,e', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/material_content_NSB.npy'), # in kg 
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['V2G_rate']= msc.Parameter(Name = 'V2G vehicles',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'v,g,t', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/V2G_ratio.npy'), # in kg 
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Capacity']= msc.Parameter(Name = 'Capacity',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'g,s,t', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/capacity.npy'),
                                                             Uncert=None,
                                                             Unit = '%')


ParameterDict['Degradation_fleet']= msc.Parameter(Name = 'Degradation',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'b,t,c', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/degradation.npy'),
                                                             Uncert=None,
                                                             Unit = '%')

ParameterDict['Degradation_slb']= msc.Parameter(Name = 'Degradation_slb',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'b,t,c', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/degradation_slb.npy'),
                                                             Uncert=None,
                                                             Unit = '%')

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


ParameterDict['Storage_demand']= msc.Parameter(Name = 'Storage_demand',
                                                             ID = 3,
                                                             P_Res = None,
                                                             MetaData = None,
                                                             Indices = 'E,t', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/Energy_storage_demand.npy'),
                                                             Uncert=None,
                                                             Unit = 'GWh')

#TODO: Add degradation NSB

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

# Add processes to system and defining flows
for m in range(0, len(PrL_Number)):
    MaTrace_System.ProcessList.append(msc.Process(Name = PrL_Name[m], ID   = PrL_Number[m]))
# %% 
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

MaTrace_System.FlowDict['B_1_2'] = msc.Flow(Name = 'Batteries from battery producer to vehicle manufacturer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_2_3'] = msc.Flow(Name = 'Batteries from battery producer to vehicle manufacturer', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_3_4'] = msc.Flow(Name = 'Outflows from use phase to ELV collection and dismantling', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,g,s,b,t,c', Values=None)
# MaTrace_System.FlowDict['B_4_5'] = msc.Flow(Name = 'Used LIBs for health assessment and dismantling', P_Start = 4, P_End = 5,
#                                             Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_4_5'] = msc.Flow(Name = 'Used LIBs as second life ', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,R,v,E,g,s,b,t,c', Values=None)
MaTrace_System.FlowDict['B_4_6'] = msc.Flow(Name = 'Spent LIBs directly to recycling', P_Start = 4, P_End = 6,
                                            Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
# MaTrace_System.FlowDict['B_6_7'] = msc.Flow(Name = 'Spent LIBs after second life to ELB collector', P_Start = 6, P_End = 7,
#                                             Indices = 'z,S,a,R,v,E,g,s,b,t', Values=None)
MaTrace_System.FlowDict['B_5_6'] = msc.Flow(Name = 'Spent LIBs after second life to to recycling', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,g,s,b,t', Values=None)
# Initializing stocks at transport stage
MaTrace_System.StockDict['B_3']   = msc.Stock(Name = 'LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_3']   = msc.Stock(Name = 'LIBs EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['B_3_V2G']   = msc.Stock(Name = 'V2G ready LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_3_V2G']   = msc.Stock(Name = 'V2G ready LIBs in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_3']  = msc.Stock(Name = 'LIBs in EV stock change', P_Res = 3, Type = 1,
                                              Indices = 'z,S,a,g,s,b,t,c', Values=None)
# Initializing stocks of SLBs at stationary storage stage
MaTrace_System.StockDict['B_5_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 5, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_5_SLB']   = msc.Stock(Name = 'SLBs in stationary storage', P_Res = 5, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_5_SLB']  = msc.Stock(Name = 'Stock change of SLBs in stationary storage', P_Res = 5, Type = 1,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
# Initializing stocks of NSB at stationary storage stage
MaTrace_System.StockDict['B_5_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 5, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_5_NSB']   = msc.Stock(Name = 'NSB in stationary storage', P_Res = 5, Type = 0,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['dB_5_NSB']  = msc.Stock(Name = 'Stock change of NSB in stationary storage', P_Res = 5, Type = 1,
                                              Indices = 'z,S,a,R,g,s,b,t,c', Values=None)

# Initialize elements layer
MaTrace_System.FlowDict['E_0_1'] = msc.Flow(Name = 'Raw materials needed for batteries', P_Start = 0, P_End = 1,
                                            Indices = 'z,S,a,R,v,E,b,e,h,t', Values=None)
MaTrace_System.FlowDict['E_1_2'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,s,b,e,t', Values=None)
MaTrace_System.FlowDict['E_2_3'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,s,b,e,t', Values=None)
MaTrace_System.FlowDict['E_3_4'] = msc.Flow(Name = 'Outflows from use phase to ELV collection and dismantling', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,b,e,t', Values=None)
# MaTrace_System.FlowDict['E_4_5'] = msc.Flow(Name = 'Used LIBs for health assessment and dismantling', P_Start = 4, P_End = 5,
#                                             Indices = 'z,S,a,b,e,t', Values=None)
MaTrace_System.FlowDict['E_4_5'] = msc.Flow(Name = 'Used LIBs as second life ', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,R,v,E,b,e,t', Values=None)
MaTrace_System.FlowDict['E_4_6'] = msc.Flow(Name = 'Spent LIBs directly to recycling', P_Start = 4, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,b,e,t', Values=None)
MaTrace_System.FlowDict['E_5_6'] = msc.Flow(Name = 'Spent LIBs after stationary storage to recycling', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,b,e,t', Values=None)
MaTrace_System.FlowDict['E_1_5'] = msc.Flow(Name = 'New batteries for stationary storage', P_Start = 1, P_End = 5,
                                            Indices = 'z,S,a,R,v,E,b,e,t', Values=None)
# MaTrace_System.FlowDict['E_7_8'] = msc.Flow(Name = 'Spent LIBs after second life to to recycling', P_Start = 7, P_End = 8,
#                                             Indices = 'z,S,a,R,v,E,b,e,t', Values=None)
MaTrace_System.FlowDict['E_6_1'] = msc.Flow(Name = 'Recycled materials materials for battery production', P_Start = 6, P_End = 1,
                                            Indices = 'z,S,a,R,v,E,b,e,h,t', Values=None)
# Initializing stocks at transport stage
MaTrace_System.StockDict['E_3']   = msc.Stock(Name = 'LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,s,b,e,t', Values=None)
MaTrace_System.StockDict['E_C_3']   = msc.Stock(Name = 'LIBs EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,s,b,e,t,c', Values=None)
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
MaTrace_System.StockDict['C_3']   = msc.Stock(Name = 'Total capacity of V2G-ready EV stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,R,v,E,t', Values=None)
MaTrace_System.StockDict['C_3_tc']   = msc.Stock(Name = 'Total capacity of V2G-ready EV stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,R,v,E,t,c', Values=None)
MaTrace_System.StockDict['Con_3']   = msc.Stock(Name = 'Capacity of share of V2G-ready EV stock connected to the grid', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,t', Values=None)
MaTrace_System.StockDict['Pcon_3']   = msc.Stock(Name = 'Power of share of V2G-ready EV stock connected to the grid', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,t', Values=None)
MaTrace_System.StockDict['C_5_SLB']   = msc.Stock(Name = 'Capacity of SLBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,E,t', Values=None)
MaTrace_System.StockDict['C_5_SLB_tc']   = msc.Stock(Name = 'Capacity of SLBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,E,g,s,b,t,c', Values=None)
MaTrace_System.StockDict['C_5_NSB']   = msc.Stock(Name = 'Capacity of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,E,t', Values=None)
MaTrace_System.StockDict['C_5_NSB_tc']   = msc.Stock(Name = 'Capacity of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,E,b,t,c', Values=None)
MaTrace_System.StockDict['Pow_3']   = msc.Stock(Name = 'Total power of V2G-ready EV stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,t', Values=None)
MaTrace_System.StockDict['Pow_5_SLB']   = msc.Stock(Name = 'Power of SLBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,t', Values=None)
MaTrace_System.StockDict['Pow_5_NSB']   = msc.Stock(Name = 'Power of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,t', Values=None)
MaTrace_System.FlowDict['C_2_3_max'] =  msc.Flow(Name = 'Capacity of vehicles equiped with V2G', P_Start = 1, P_End = 6,
                                            Indices = 'z,S,a,v,g,s,b,t', Values=None) # Only in terms of capacity
MaTrace_System.FlowDict['C_2_3_real'] =  msc.Flow(Name = 'Capacity of vehicles equiped with V2G', P_Start = 1, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,t', Values=None) # Only in terms of capacity
MaTrace_System.FlowDict['C_1_5'] =  msc.Flow(Name = 'New LIBs for stationary storage ', P_Start = 1, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,b,t', Values=None) # Only in terms of capacity
MaTrace_System.FlowDict['C_4_5'] =  msc.Flow(Name = 'Used LIBs for stationary storage ', P_Start = 1, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,g,s,b,t', Values=None) # Only in terms of capacity
MaTrace_System.FlowDict['C_5_6_SLB'] =  msc.Flow(Name = 'Spent LIBs to recycling', P_Start = 1, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,g,s,b,t', Values=None) # Only in terms of capacity
MaTrace_System.FlowDict['C_5_6_NSB'] =  msc.Flow(Name = 'New LIBs for stationary storage outflows', P_Start = 5, P_End = 6,
                                             Indices = 'z,S,a,R,v,E,b,t', Values=None) # Only in terms of capacity
MaTrace_System.Initialize_FlowValues()  # Assign empty arrays to flows according to dimensions.
MaTrace_System.Initialize_StockValues() # Assign empty arrays to flows according to dimensions.

### Define lifetimes to be used in the model
'''
We use a single lifetime approach under the assumption that no battery replacements or reuse
in the transport sector are allowed. We further assume that the battery lifetime is the 
main limitting factor to vehicle lifetime and that they leave the fleet once the capacity
reaches 80% of the original value. The lifetime distribution helps to reflect the uncertainty
in driving patterns and other conditions that affect the time a battery can be useful for. 
'''
# lt_bat = np.array([12])
# sd_bat = np.array([3])

lt_car = np.array([12])
sd_car = np.array([3])



# %% 
print('Running model')
for z in range(Nz):
    for g in range(0,Ng):
        for S in range(NS):
            Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,:]/1000, \
                lt_pr = {'Type': 'Normal', 'Mean': lt_car, 'StdDev': sd_car })
            Model.case_1()
            # Vehicles layer
            MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:]           = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:] ,\
                np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
            MaTrace_System.StockDict['S_3'].Values[z,S,g,:,:]               = np.einsum('stc->st', MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:])
            MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:,:]              = np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:],\
                np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
            MaTrace_System.FlowDict['V_3_4'].Values[z,S,g,:,:,:]            = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:],\
                np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))

            ###  LIBs layer, we calculate the stocks anew but this time via the battery dynamics S_C_bat --> This is only important if we want to implement different lt for the battery
            MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:]       = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , \
                np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:], \
                np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
            MaTrace_System.StockDict['B_3'].Values[z,S,:,g,:,:,:]           = np.einsum('asbtc->asbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:])
            ### Calculate share of stock with V2G
            MaTrace_System.StockDict['B_C_3_V2G'].Values[z,S,:,:,g,:,:,:,:]     = np.einsum('vc,asbtc->avsbtc',MaTrace_System.ParameterDict['V2G_rate'].Values[:,g,:], \
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:])
            MaTrace_System.StockDict['B_3_V2G'].Values[z,S,:,:,g,:,:,:]         = np.einsum('avsbtc->avsbt', MaTrace_System.StockDict['B_C_3_V2G'].Values[z,S,:,:,g,:,:,:,:])
            # Calculating battery inflow in the vehicles
            MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,g,:,:,:]          = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , \
                MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:,:])
            # Calculating batteryy demand to battery manufacturer including reuse and replacements
            MaTrace_System.FlowDict['B_1_2'].Values[z,S,:,g,:,:,:]            = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:], \
                np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy())))
            # Calculating the outflows based on the battery demand. 
            # At the moment: LIB flows = EV flows
            MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]        = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[S,g,:,:], \
                np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_cm.copy())))
            # MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]
            '''
            We calculate the flows of batteries into reuse. Strictly speaking, only the modules are reused and the casing and other components
            go directly into recycling. However, since we are only interested in the materials in the battery cells, this does not play a role. 
            
            It makes sense to consider all batteries that flow out of the vehicle fleet, including the battery failures. This is because the 
            requirements for the battery to be considered "functional" are higher in transport than in stationary application, i.e. a battery
            considered failed for transport may still be fine for stationary storage. 

            The reuse parameter does not indicate the share of batteries that are reused. Rather, it is a condition to reflect decisions about
            which battery chemistries are considered for reuse. LFP scenario for instance will define that only LFP chemistries are considered 
            for reuse, but the health assessment still needs to happen. 

            Flow B_4_5 should be considered the maximum amount of batteries that are available for reuse, but that will not necessarily be
            reused if there is not sufficient demand. 
            '''
            for v in range(Nv):
                for E in range(NE):
                    for t in range(Nt):
                        for c in range(t):
                            # FIXME: Don't need all those loops, I think
                            # Calculate maximum inflows available to SLB:
                            MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,:,v,E,g,:,:,t,c]  = np.einsum('Rb,asb->aRsb', MaTrace_System.ParameterDict['Reuse_rate'].Values[:,:,t], \
                                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,t,c]) 

            '''
            Since the batteries are moving from being used in transport to being used in stationary storage, the "lifetime" is no longer the same. 
            In transportation, we define the lifetime to be the time that the battery is still useful for that purpose, which is widely considered
            to be until it reaches 80% of its initial capacity. The distribution of the lifetime helps us account for batteries that are more 
            intensely used than others, but by the time of outflow they should all have more or less the same capacity of around 80%. 

            Therefore, the remaining second life can be approximated with a normal distribution that would have an initial capacity of 80% and would
            follow its own degradation curve until the battery is no longer useable for stationary applications either. We assume that this point is
            reached once the battery has only 60% of its initial capacity left. 
            '''


'''
Now we define the energy layer, where we need to calculate the capacity in the fleet as a whole, 
the capacity available for V2G, and the capacity available from stationary storage. Once this
is calculated, we can compare that to the total demand and compute the necessary additional
stationary storage (if any) to satisfy that demand. then the ourflows after stationary storage 
need to be calculated using a model for that as well. 
'''
# %%
'''
Here we will introduce a new way of computing things. Essentially, the underlying assumption
would be that if there is no demand for stationary storage, then there is no need for further
implementing V2G or SLBs. This means that we need some sort of prioritizing system which I 
propose be: 1) V2G, if not enough 2) SLB, and if still not enough 3) NSB. 

The scenarios for the reuse and V2G penetration would then be kind of the maximum available
capacity per technology, but if not all is used then the excess capacity it is neglected. 

We assume that the lifetime for batteries in stationary storage is longer than for the batteries
in vehicles, since they are less intensively used. 
'''
# Defining new battery lifetime and standard deviation
# TODO: Do these values make sense? If we are choosing 12yrs in vehicles + 6yrs in second life, then 12 have a mean of 18yrs which is more than the 16 assumed here. Maybe we should go for 20 to remain consistent?
Model_nsb = pcm.ProductComponentModel(t = range(0,Nt),  lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4])})
Model_nsb.compute_sf_pr()

# Defining second life battery lifetime
lt_slb                               = np.array([6]) 
sd_slb                               = np.array([2]) 
slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb})
slb_model.compute_sf()

# Aggregate all cohorts for reuse under the assumption that they are in similar SOH
inflows = np.einsum('zSaRvEgsbtc->zSaRvEgsbt',MaTrace_System.FlowDict['B_4_5'].Values[:,:,:,:,:,:,:,:,:,:,:])
# Calculate the capacity that is available according to this under the assumption that 80% of the initial capacity is still available
SLB_available = np.einsum('zSaRvEgsbt, gst->zSaRvEgsbt',inflows, MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]) * 0.8 
# Calculate the maximum amount of vehicles that can be equipped with V2G. We assume that the plug-ratio is 50% and park ratio is also 50%. Therefore we use factor 0.25
MaTrace_System.FlowDict['C_2_3_max'].Values[:,:,:,:,:,:,:,:]         = np.einsum('vgt, zSagsbt->zSavgsbt',MaTrace_System.ParameterDict['V2G_rate'].Values[:,:,:], \
    np.einsum('btc,zSagsbtc->zSagsbt', MaTrace_System.ParameterDict['Degradation_fleet'].Values[:,:,:], \
                np.einsum('zSagsbt, gsc->zSagsbtc', MaTrace_System.FlowDict['B_2_3'].Values[:,:,:,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[:,:,:]))) *0.25

'''
Since the flows have been adjusted to the demand, we need to update the values of SLBs as not
all batteries available are actually reused. V2G has a similar issue, as we would like to 
avoid installing a lot of V2G capable vehicles that cannot be used.

Knowing the V2G and SLB available capacity, we can calculate the demand for new batteries. 
We can define a degradation curve that is less steep than the one on EV batteries
since the requirements in this application are lower. This in turn means a longer lifetime. 

For now I assume all NSB are LFP since I don't have material data on teh other chemistries yet.
'''
# %%
installed_slbs = np.zeros((Nz, NS ,Na, NR, Nv, NE, Nt))
share_reused = np.ones((Nz, NS ,Na, NR, Nv, NE, Nt))

print('Calculating energy layer')
for z in range(Nz):
    for S in range(NS):
        for a in range(Na):
            for v in range(Nv):
                for R in range(NR):
                    for E in range(NE):
                        for t in range(Nt):
                            # If the demand exceeds installed capacity and potential V2G, install all V2G available
                            # FIXME: Add degradation curves
                            if MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,t] \
                                + MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,t] \
                                    + MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,t] \
                                        + np.sum(MaTrace_System.FlowDict['C_2_3_max'].Values[z,S,a,v,:,:,:,t])\
                                        <  MaTrace_System.ParameterDict['Storage_demand'].Values[E,t]:
                                        MaTrace_System.FlowDict['C_2_3_real'].Values[z,S,a,R,v,E,t]   = np.sum(MaTrace_System.FlowDict['C_2_3_max'].Values[z,S,a,v,:,:,:,t])
                                        # FIXME: Currently assuming all chemistries degrade the same in the fleet
                                        MaTrace_System.StockDict['C_3_tc'].Values[z,S,a,R,v,E,t::,t]        = MaTrace_System.FlowDict['C_2_3_real'].Values[z,S,a,R,v,E,t] * Model.sf_pr[t::,t] * MaTrace_System.ParameterDict['Degradation_fleet'].Values[0,t::,t]
                                        MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,:]               = np.einsum('tc->t',MaTrace_System.StockDict['C_3_tc'].Values[z,S,a,R,v,E,:,:])
                                        # If there is still demand after V2G is installed, and the available SLBs are all needed, we install all SLBs
                                        if MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,t] \
                                            + MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,t] \
                                                + MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,t] \
                                                    + np.sum(SLB_available[z,S,a,R,v,E,:,:,:,t]) < MaTrace_System.ParameterDict['Storage_demand'].Values[E,t]:
                                                    MaTrace_System.FlowDict['C_4_5'].Values[z,S,a,R,v,E,:,:,:,t]            = SLB_available[z,S,a,R,v,E,:,:,:,t]
                                                    for g in range(Ng):
                                                        for s in range(Ns):
                                                            for b in range(Nb):
                                                                MaTrace_System.StockDict['C_5_SLB_tc'].Values[z,S,a,R,v,E,g,s,b,t::,t]  = MaTrace_System.FlowDict['C_4_5'].Values[z,S,a,R,v,E,g,s,b,t] * slb_model.sf[t::,t] * MaTrace_System.ParameterDict['Degradation_slb'].Values[b,t::,t]
                                                    MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,:]               = np.einsum('gsbtc->t', MaTrace_System.StockDict['C_5_SLB_tc'].Values[z,S,a,R,v,E,:,:,:,:,:])
                                                    # Fill gap with new LFP batteries
                                                    MaTrace_System.FlowDict['C_1_5'].Values[z,S,a,R,v,E,2,t]                = max(MaTrace_System.ParameterDict['Storage_demand'].Values[E,t] \
                                                        - MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,t] - MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,t] \
                                                            - MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,t], 0)
                                                    # TODO: Add degradation NSB
                                                    MaTrace_System.StockDict['C_5_NSB_tc'].Values[z,S,a,R,v,E,2,t::,t]        = MaTrace_System.FlowDict['C_1_5'].Values[z,S,a,R,v,E,2,t] * Model_nsb.sf_pr[t::,t]
                                                    MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,:]               = np.einsum('tc->t', MaTrace_System.StockDict['C_5_NSB_tc'].Values[z,S,a,R,v,E,2,:,:])
                                        # If V2G + SLBs exceeds demand, only reuse as many as are needed to meet it
                                        elif MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,t] \
                                            + MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,t] \
                                                + MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,t] \
                                                    + np.sum(SLB_available[z,S,a,R,v,E,:,:,:,t]) >= MaTrace_System.ParameterDict['Storage_demand'].Values[E,t]:
                                            installed_slbs[z,S,a,R,v,E,t]    =  MaTrace_System.ParameterDict['Storage_demand'].Values[E,t] - MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,t]\
                                                - MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,t] - MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,t]
                                            # We define the share of SLBs that is actually installed as the available batteries times the ratio of batteries installed to available. 
                                            # All chemistries given the same priority
                                            share_reused[z,S,a,R,v,E,t]                                  =   (installed_slbs[z,S,a,R,v,E,t]/np.sum(SLB_available[z,S,a,R,v,E,:,:,:,t]))
                                            MaTrace_System.FlowDict['C_4_5'].Values[z,S,a,R,v,E,:,:,:,t] = SLB_available[z,S,a,R,v,E,:,:,:,t] * share_reused[z,S,a,R,v,E,t]
                                            for g in range(Ng):
                                                for s in range(Ns):
                                                    for b in range(Nb):
                                                        MaTrace_System.StockDict['C_5_SLB_tc'].Values[z,S,a,R,v,E,g,s,b,t::,t]  = MaTrace_System.FlowDict['C_4_5'].Values[z,S,a,R,v,E,g,s,b,t] * slb_model.sf[t::,t] * MaTrace_System.ParameterDict['Degradation_slb'].Values[b,t::,t]
                                            MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,:]               = np.einsum('gsbtc->t', MaTrace_System.StockDict['C_5_SLB_tc'].Values[z,S,a,R,v,E,:,:,:,:,:])
                            else: 
                                MaTrace_System.FlowDict['C_2_3_real'].Values[z,S,a,R,v,E,t] = max(MaTrace_System.ParameterDict['Storage_demand'].Values[E,t] - MaTrace_System.StockDict['C_5_SLB'].Values[z,S,a,R,v,E,t]\
                                           - MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,t] - MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,t], 0)
                                MaTrace_System.StockDict['C_3_tc'].Values[z,S,a,R,v,E,t::,t]        = MaTrace_System.FlowDict['C_2_3_real'].Values[z,S,a,R,v,E,t] * Model.sf_pr[t::,t] * MaTrace_System.ParameterDict['Degradation_fleet'].Values[0,t::,t]
                                MaTrace_System.StockDict['C_3'].Values[z,S,a,R,v,E,:]               = np.einsum('tc->t',MaTrace_System.StockDict['C_3_tc'].Values[z,S,a,R,v,E,:,:])
                        # Calculate outflows
                        MaTrace_System.FlowDict['C_5_6_SLB'].Values[z,S,a,R,v,E,:,:,:,1:]           = MaTrace_System.FlowDict['C_4_5'].Values[z,S,a,R,v,E,:,:,:,1:] - np.diff((MaTrace_System.StockDict['C_5_SLB_tc'].Values[z,S,a,R,v,E,:,:,:,:,:]).sum(axis=-1), n=1,axis=-1)
                        MaTrace_System.FlowDict['C_5_6_NSB'].Values[z,S,a,R,v,E,2,1:]               = MaTrace_System.FlowDict['C_1_5'].Values[z,S,a,R,v,E,2,1:] - np.diff(MaTrace_System.StockDict['C_5_NSB'].Values[z,S,a,R,v,E,:], n=1,axis=0)
                        # Calculate real share that got reused
                        MaTrace_System.FlowDict['B_4_5'].Values[z,S,a,R,v,E,:,:,:,:,:]              = MaTrace_System.FlowDict['B_4_5'].Values[z,S,a,R,v,E,:,:,:,:,:]* share_reused[z,S,a,R,v,E,:]
                        # Calculate outflow volume of SLBs
                        for b in range(Nb):
                            MaTrace_System.FlowDict['B_5_6'].Values[z,S,a,R,v,E,1,:,b,:]             = MaTrace_System.FlowDict['C_5_6_SLB'].Values[z,S,a,R,v,E,1,:,b,:] / (MaTrace_System.ParameterDict['Capacity'].Values[1,:,:]*0.8) # TODO: Adjust once degradation is implemented

'''
Here we calculate the material flows for Ni, Co, Li, P, C, Mn, which are materials exclusively in modules.
Since we are only interested in the cell materials, we define the material content based on the size of the battery 
independently of whether that battery has been dismantled or not (cell material content does not change in this process).
See material_content.ipynb for a detailed description and data for the calculations. 

We aggregate the cohorts to have the total flows, as the cohort composition is not interesting in the 
context of materials. 
'''
# %%
print('Running element layer')
for z in range(Nz):
    for g in range(0,Ng):
        for S in range(NS): 
            MaTrace_System.StockDict['E_C_3'].Values[z,S,:,:,:,:,:,:]     = np.einsum('gsbe, agsbtc->asbetc', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], \
                MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,:,:,:,:])
            MaTrace_System.StockDict['E_3'].Values[z,S,:,:,:,:,:]         = np.einsum('asbetc->asbet', MaTrace_System.StockDict['E_C_3'].Values[z,S,:,:,:,:,:,:])
            # Calculate inflows 
            MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,:,:,:,:]        = np.einsum('gsbe,agsbt->asbet',MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], \
                MaTrace_System.FlowDict['B_1_2'].Values[z,S,:,:,:,:,:])
            MaTrace_System.FlowDict['E_2_3'].Values[z,S,:,:,:,:,:]        = MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,:,:,:,:]
            # Calculate outflows
            MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,:,:,:]            = np.einsum('gsbe,agsbtc->abet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], \
                MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,:,:,:,:,:])
            # MaTrace_System.FlowDict['E_4_5'].Values[z,S,:,:,:,:]            = MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,:,:,:]
            # Calculate flows at second life: Aggregate segments as no longer relevant
            MaTrace_System.FlowDict['E_4_5'].Values[z,S,:,:,:,:,:,:,:]      = np.einsum('gsbe,aRvEgsbtc->aRvEbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], \
                MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,:,:,:,:,:,:,:,:])
            MaTrace_System.FlowDict['E_5_6'].Values[z,S,:,:,:,:,:,:,:]      = np.einsum('gsbe,aRvEgsbt->aRvEbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], \
                MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,:,:,:,:,:]) \
                        + np.einsum('gbe,aRvEbt->aRvEbet',MaTrace_System.ParameterDict['Material_content_NSB'].Values[:,:,:], \
                            MaTrace_System.FlowDict['C_5_6_NSB'].Values[z,S,:,:,:,:,:,:])
            # Calculate material stock? Slows down model and not necessarily insightful
            # Calculate recycling flows
            for R in range(NR):
                for v in range(Nv):
                    for E in range(NE):
                        MaTrace_System.FlowDict['E_4_6'].Values[z,S,:,R,v,E,:,:,:]      = MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,:,:,:] - MaTrace_System.FlowDict['E_4_5'].Values[z,S,:,R,v,E,:,:,:]
                        MaTrace_System.FlowDict['E_1_5'].Values[z,S,:,R,v,E,:,:,:]      = np.einsum('gbe,abt->abet',MaTrace_System.ParameterDict['Material_content_NSB'].Values[:,:,:], \
                            MaTrace_System.FlowDict['C_1_5'].Values[z,S,:,R,v,E,:,:])
            # Flows of batteries to recycling after reuse
            MaTrace_System.FlowDict['E_5_6'].Values[z,S,:,:,:,:,:]          = np.einsum('gsbe,aRvEgsbt->aRvEbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], \
                MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,:,:,:,:,:]) 
            # FIXME: Add NSB outflows
            # Calculate recovered materials for different recycling technologies and corresponding promary material demand
            for v in range(Nv):
                for E in range(NE):
                    # Recoverred materials come from SLBs + directly recycled batteries + new batteries
                    MaTrace_System.FlowDict['E_6_1'].Values[z,S,:,:,v,E,:,:,:,:]        = np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], \
                        MaTrace_System.FlowDict['E_5_6'].Values[z,S,:,:,v,E,:,:,:]) +\
                        np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], MaTrace_System.FlowDict['E_4_6'].Values[z,S,:,:,v,E,:,:,:]) \
                            + np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], \
                                np.einsum('gbe,aRbt->aRbet',MaTrace_System.ParameterDict['Material_content_NSB'].Values[:,:,:], MaTrace_System.FlowDict['C_5_6_NSB'].Values[z,S,:,:,v,E,:,:]))
            # Calculate demand for primary materials
            for R in range(NR):
                for h in range(Nh):
                    for v in range(Nv):
                        for E in range(NE):
                            # Primary material demand is the batteries that are needed for vehicles + batteries that are needed for stationary storage - recoverred materials
                            MaTrace_System.FlowDict['E_0_1'].Values[z,S,:,R,v,E,:,:,h,:]    = np.einsum('asbet->abet', MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,:,:,:,:]) - \
                                MaTrace_System.FlowDict['E_6_1'].Values[z,S,:,R,v,E,:,:,h,:] + MaTrace_System.FlowDict['E_1_5'].Values[z,S,:,R,v,E,:,:,:]#
                    
'''
I suggest that for the moment, before we spend too much time visualizing the results in a fancy way,
we use the scenario_visualizations.py tool to gain an overview of the model results. We can then decide 
what is insightful and meaningful as a figure and can create those figures for the manuscript. 
# '''
# # %%
# print('Exporting results')
# # Exporting vehicle flows
# results = os.path.join(os.getcwd(), 'results')
# #np.save('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/inflows/inflow_array', np.einsum('zSrgt->zSrt', MaTrace_System.FlowDict['Inflows'].Values[:,:,:,:,:]), allow_pickle=True)
# np.save(results+'/arrays/vehicle_stock_array', np.einsum('zSgst->zSgt', MaTrace_System.StockDict['S_3'].Values[:,:,:,:,:]), allow_pickle=True)
# np.save(results+'/arrays/vehicle_outflow_array', np.einsum('zSgstc->zSgt', MaTrace_System.FlowDict['V_3_4'].Values[:,:,:,:,:,:]), allow_pickle=True)
# np.save(results+'/arrays/vehicle_inflow_array', np.einsum('zSgst->zSgt', MaTrace_System.FlowDict['V_2_3'].Values[:,:,:,:,:]), allow_pickle=True)

# # Exporting battery flows
# np.save(results+'/arrays/battery_inflow_array', np.einsum('zSagsbt->zSabt', MaTrace_System.FlowDict['B_2_3'].Values[:,:,:,:,:,:,:]), allow_pickle=True) 
# np.save(results+'/arrays/battery_outflow_array', np.einsum('zSagsbtc->zSabt', MaTrace_System.FlowDict['B_3_4'].Values[:,:,:,:,:,:,:,:]), allow_pickle=True) 
# np.save(results+'/arrays/battery_reuse_array', np.einsum('zSaRgsbtc->zSaRbt', MaTrace_System.FlowDict['B_5_6'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) 
# np.save(results+'/arrays/battery_reuse_to_recycling_array',  np.einsum('zSaRgsbtc->zSaRbt',MaTrace_System.FlowDict['B_7_8'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True) 
# np.save(results+'/arrays/battery_recycling_array',  np.einsum('zSaRgsbtc->zSaRbt',MaTrace_System.FlowDict['B_5_8'].Values[:,:,:,:,:,:,:,:,:]), allow_pickle=True)
# np.save(results+'/arrays/slb_stock_array', np.einsum('zSaRgsbt->zSaRbt',MaTrace_System.StockDict['B_6_SLB'].Values[:,:,:,:,:,:,:,:]), allow_pickle=True) 


# # Exporting material flows
# np.save(results+'/arrays/material_inflow_array',  np.einsum('zSasbet->zSaet',MaTrace_System.FlowDict['E_1_2'].Values), allow_pickle=True) 
# np.save(results+'/arrays/material_outflow_array', np.einsum('zSabet->zSaet', MaTrace_System.FlowDict['E_3_4'].Values), allow_pickle=True) 
# np.save(results+'/arrays/material_reuse_array', np.einsum('zSaRbet->zSaRet', MaTrace_System.FlowDict['E_5_6'].Values), allow_pickle=True) 
# np.save(results+'/arrays/material_reuse_to_recycling_array',  np.einsum('zSaRbet->zSaRet',MaTrace_System.FlowDict['E_7_8'].Values), allow_pickle=True) 
# np.save(results+'/arrays/material_recycling_array',  np.einsum('zSaRbet->zSaRet' ,MaTrace_System.FlowDict['E_5_8'].Values), allow_pickle=True)
# np.save(results+'/arrays/material_recycled_process_array', np.einsum('zSaRbeht->zSaReht', MaTrace_System.FlowDict['E_8_1'].Values), allow_pickle=True)
# np.save(results+'/arrays/material_primary_array', np.einsum('zSaRbeht->zSaReht', MaTrace_System.FlowDict['E_0_1'].Values), allow_pickle=True)

#%%
## Exporting P values Anna
def export_P_values():
    results = os.path.join(os.getcwd(), 'results')
    np.save(results+'/arrays/P_demand_vehicles',np.einsum('zSasbt->zSat',MaTrace_System.FlowDict['E_1_2'].Values[:,:,:,:,:,2,:]), allow_pickle=True)# z,S,a,s,b,e,t


## Exporting table with key indicators
def export_table():
    import seaborn as sns
    a = 5 # Faraday chemistry scenario
    h = 1 # Hydrometallurgical recycling
    table = []
    # Exporting primary material use
    z = 1
    for S in range(NS):
        for R in range(NR):
            for v in range(Nv):
                for E in range(NE):
                    scenario = pd.DataFrame({'EV Scenario':[IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[S]], \
                                'Reuse Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items[R]], \
                                    'V2G Scenario':[IndexTable.Classification[IndexTable.index.get_loc('V2G_Scenarios')].Items[v]], \
                                        'Storage Demand Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Energy_Storage_Scenarios')].Items[E]], \
                                            'Primary materials': [np.einsum('bet->', MaTrace_System.FlowDict['E_0_1'].Values[z,S,a,R,v,E,:,:,h,:])]})
                    table.append(scenario)
    material_scenarios = pd.concat(table)
    material_scenarios.reset_index(inplace=True, drop=True)
    cm = sns.light_palette("red", as_cmap=True)
    material_scenarios = material_scenarios.style.background_gradient(cmap=cm)
    
    # Exporting recycled material use
    rec = []
    for S in range(NS):
        for R in range(NR):
            for v in range(Nv):
                for E in range(NE):
                    rec_scenario = pd.DataFrame({
                            'EV Scenario':[IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[S]], \
                                'Reuse Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items[R]], \
                                    'V2G Scenario':[IndexTable.Classification[IndexTable.index.get_loc('V2G_Scenarios')].Items[v]], \
                                        'Storage Demand Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Energy_Storage_Scenarios')].Items[E]], \
                                            'Secondary materials': [np.einsum('bet->', MaTrace_System.FlowDict['E_6_1'].Values[z,S,a,R,v,E,:,:,h,:])]})
                    rec.append(rec_scenario)
    recycled = pd.concat(rec)
    recycled.reset_index(inplace=True, drop=True)
    cm = sns.light_palette("green", as_cmap=True)
    recycled = recycled.style.background_gradient(cmap=cm)
    
    ## Export amount of batteries reused
    reuse = []
    for S in range(NS):
        for R in range(NR):
            for v in range(Nv):
                for E in range(NE):
                    reuse_scenario = pd.DataFrame({
                            'EV Scenario':[IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[S]], \
                                'Reuse Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items[R]], \
                                    'V2G Scenario':[IndexTable.Classification[IndexTable.index.get_loc('V2G_Scenarios')].Items[v]], \
                                        'Storage Demand Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Energy_Storage_Scenarios')].Items[E]], \
                                            'Reused batteries': [np.einsum('gsbt->', MaTrace_System.FlowDict['C_4_5'].Values[z,S,a,R,v,E,:,:,:,:])]})
                    reuse.append(reuse_scenario)
    reused = pd.concat(reuse)
    reused.reset_index(inplace=True, drop=True)
    cm = sns.light_palette("green", as_cmap=True)
    reused = reused.style.background_gradient(cmap=cm)
    
    ## Export amount of new batteries 
    new = []
    for S in range(NS):
        for R in range(NR):
            for v in range(Nv):
                for E in range(NE):
                    new_scenario = pd.DataFrame({
                            'EV Scenario':[IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[S]], \
                                'Reuse Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items[R]], \
                                    'V2G Scenario':[IndexTable.Classification[IndexTable.index.get_loc('V2G_Scenarios')].Items[v]], \
                                        'Storage Demand Scenario':[IndexTable.Classification[IndexTable.index.get_loc('Energy_Storage_Scenarios')].Items[E]], \
                                            'New batteries': [np.einsum('bt->', MaTrace_System.FlowDict['C_1_5'].Values[z,S,a,R,v,E,:,:])]})
                    new.append(new_scenario)
    new_bat = pd.concat(new)
    new_bat.reset_index(inplace=True, drop=True)
    cm = sns.light_palette("red", as_cmap=True)
    new_bat = new_bat.style.background_gradient(cmap=cm)
                        
                        
    # Create a Pandas Excel writer using XlsxWriter as the engine.
    writer = pd.ExcelWriter(os.path.join(os.getcwd(), 'results/Manuscript/material_use.xlsx'), engine='xlsxwriter')

    # Write each dataframe to a different worksheet.
    material_scenarios.to_excel(writer, sheet_name='Primary materials')
    recycled.to_excel(writer, sheet_name='Secondary materials')
    reused.to_excel(writer, sheet_name='Reused batteries')
    new_bat.to_excel(writer, sheet_name='New batteries')
    # Close the Pandas Excel writer and output the Excel file.
    writer.save()
       
# %% 
def plot_V2G_scenarios():
    from cycler import cycler
    import seaborn as sns
    scen_cycler = (cycler(color=['red','green', 'blue']) *
          cycler(linestyle=['-','--',':']))    
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 0 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g
    e = 2 # Low, medium, high
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(scen_cycler)
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[0,70::], '--k')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[2,70::], 'xk')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[3,70::], 'k')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,0,a,0,:,70::].sum(axis=0), '-r')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,0,a,2,:,70::].sum(axis=0))
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,0,a,3,:,70::].sum(axis=0))
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,1,a,0,:,70::].sum(axis=0))
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,1,a,2,:,70::].sum(axis=0))
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,1,a,3,:,70::].sum(axis=0))
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Low storage demand','Medium storage demand','High storage demand', 'V2G low, Slow EV', 'V2G moderate, Slow EV', 'V2G mandate, Slow EV', 'V2G low, Fast EV', 'V2G moderate, Fast EV', 'V2G mandate, Fast EV'], loc='upper left',prop={'size':15})
    ax.set_title('Available V2G capacity by scenario'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,6000)
    plt.savefig(os.path.join(os.getcwd(), 'results/Manuscript/V2G_scenarios'))

# %% 
def plot_SLB_scenarios():
    from cycler import cycler
    import seaborn as sns
    scen_cycler = (cycler(color=['red','green']) *
          cycler(linestyle=['-','--'])) 
    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 1 # NCX, LFP, Next_Gen, Roskill, BNEF, Faraday
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g
    e = 2 # Low, medium, high
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(scen_cycler)
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[0,70::], '--k')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[2,70::], 'xk')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[3,70::], 'k')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,0,a,0,:,70::].sum(axis=0))
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,0,a,2,:,70::].sum(axis=0))
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,1,a,0,:,70::].sum(axis=0))
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,1,a,2,:,70::].sum(axis=0))
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Low storage demand','Medium storage demand','High storage demand', 'LFP reused - Slow EV', 'All reused - Slow EV', 'LFP reused - Fast EV', 'All reused - Fast EV'], loc='upper left',prop={'size':15})
    ax.set_title('Available SLB capacity by scenario'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,6000)
    plt.savefig(os.path.join(os.getcwd(), 'results/Manuscript/SLB_scenarios'))
# %%
def plot_energy_resource_graphs():
    from cycler import cycler
    import seaborn as sns
    custom_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu'
    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax.set_title('Available capacity by technology'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.text(2005, 700, 'Baseline stock and electrification', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 550, 'Faraday Inst. tech. ', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 400, 'No reuse', style='italic',
            bbox={'facecolor': 'blue', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 250, 'No V2G', style='italic',
            bbox={'facecolor': 'blue', 'alpha': 0.3, 'pad': 10}, fontsize=15)
            
    ax.text(2005, 100, 'High demand', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    #ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,1300)
    material_cycler = cycler(color=['r','g','b','yellow','m','k', 'indianred', 'yellowgreen', 'cornflowerblue', 'palegoldenrod', 'plum', 'lightgrey']) #'Set2', 'Paired', 'YlGnBu'

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(material_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0),\
                    MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0))
    ax.legend(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[:]+['Rec. Li', 'Rec. Graphite', 'Rec. P', 'Rec. Mn', 'Rec. Co', 'Rec. Ni'], loc='upper left',prop={'size':15})
    ax.set_ylabel('Material weight [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Material demand'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,3000)

    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 3 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax.set_title('Available capacity by technology'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.text(2005, 700, 'Baseline stock and electrification', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 550, 'Faraday Inst. tech.', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 400, 'No reuse', style='italic',
            bbox={'facecolor': 'blue', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 250, 'V2G mandate from 2027', style='italic',
            bbox={'facecolor': 'blue', 'alpha': 0.3, 'pad': 10}, fontsize=15)
            
    ax.text(2005, 100, 'High demand', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    #ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,1300)
    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(material_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0),\
                    MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0))
    ax.legend(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[:]+['Rec. Li', 'Rec. Graphite', 'Rec. P', 'Rec. Mn', 'Rec. Co', 'Rec. Ni'], loc='upper left',prop={'size':15})
    ax.set_ylabel('Material weight [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Material demand'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,3000)

    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 2 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, V2G mandate, No V2G, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax.set_title('Available capacity by technology'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.text(2005, 700, 'Baseline stock and electrification', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 550, 'Faraday Inst. tech.', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 400, 'All reused', style='italic',
            bbox={'facecolor': 'blue', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 250, 'No V2G', style='italic',
            bbox={'facecolor': 'blue', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 100, 'High demand', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,1300)

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(material_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0),\
                    MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0))
    ax.legend(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[:]+['Rec. Li', 'Rec. Graphite', 'Rec. P', 'Rec. Mn', 'Rec. Co', 'Rec. Ni'], loc='upper left',prop={'size':15})
    ax.set_ylabel('Material weight [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Material demand'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,3000)

# %%
def plot_energy_resource_aggregated():
    from cycler import cycler
    import seaborn as sns
    custom_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu'
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax.set_title('Available capacity by technology'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,1300)
    material_cycler = cycler(color=sns.color_palette('Paired', 6))

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(material_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    ax.legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax.set_ylabel('Material weight [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Material demand'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,-1]) + np.einsum('bm->', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    plt.ylim(0,3000)

    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 3 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax.set_title('Available capacity by technology'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,1300)
    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(material_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    ax.legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax.set_ylabel('Material weight [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Material demand'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,-1]) + np.einsum('bm->', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,3000)

    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 2 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, V2G mandate, No V2G, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax.set_title('Available capacity by technology'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,1300)

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(material_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    ax.legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax.set_ylabel('Material weight [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Material demand'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    print(np.einsum('bm->', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,-1]) + np.einsum('bm->', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,-1]))
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,3000)

# %%
def plot_energy_resource_multi():
    from cycler import cycler
    import seaborn as sns
    
    custom_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu'
    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(4,3,figsize=(13,16), sharex=True)
    ax[0,0].set_prop_cycle(custom_cycler)
    ax[0,0].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax[0,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax[0,0].set_ylabel('Capacity [GWh]',fontsize =8)
    right_side = ax[0,0].spines["right"]
    right_side.set_visible(False)
    top = ax[0,0].spines["top"]
    top.set_visible(False)
    # ax[0,0].legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax[0,0].set_title('Available capacity by technology'.format(S), fontsize=8)
    ax[0,0].set_xlabel('Year',fontsize =8)
    ax[0,0].tick_params(axis='both', which='major', labelsize=8)
    plt.ylim(0,1300)
    material_cycler = cycler(color=sns.color_palette('Paired', 6))

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    ax[1,0].set_prop_cycle(material_cycler)
    ax[1,0].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    # ax[1,0].legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax[1,0].set_ylabel('Material weight [kt]',fontsize =8)
    right_side = ax[1,0].spines["right"]
    right_side.set_visible(False)
    top = ax[1,0].spines["top"]
    top.set_visible(False)
    ax[1,0].set_title('Material demand'.format(S), fontsize=8)
    ax[1,0].set_xlabel('Year',fontsize =8)
    ax[1,0].tick_params(axis='both', which='major', labelsize=8)
    ax[1,0].set_ylim(0,3000)

    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 3 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    ax[0,1].set_prop_cycle(custom_cycler)
    ax[0,1].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax[0,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax[0,1].set_ylabel('Capacity [GWh]',fontsize =8)
    right_side = ax[0,1].spines["right"]
    right_side.set_visible(False)
    top = ax[0,1].spines["top"]
    top.set_visible(False)
    # ax[0,1].legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax[0,1].set_title('Available capacity by technology'.format(S), fontsize=8)
    ax[0,1].set_xlabel('Year',fontsize =8)
    ax[0,1].tick_params(axis='both', which='major', labelsize=8)
    plt.ylim(0,1300)
    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    ax[1,1].set_prop_cycle(material_cycler)
    ax[1,1].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    # ax[1,1].legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax[1,1].set_ylabel('Material weight [kt]',fontsize =8)
    right_side = ax[1,1].spines["right"]
    right_side.set_visible(False)
    top = ax[1,1].spines["top"]
    top.set_visible(False)
    ax[1,1].set_title('Material demand'.format(S), fontsize=8)
    ax[1,1].set_xlabel('Year',fontsize =8)
    ax[1,1].tick_params(axis='both', which='major', labelsize=8)
    ax[1,1].set_ylim(0,3000)
    
    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 2 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, V2G mandate, No V2G, early
    e = 3 # Low, medium, high, CP4All
    ax[0,2].set_prop_cycle(custom_cycler)
    ax[0,2].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax[0,2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax[0,2].set_ylabel('Capacity [GWh]',fontsize =8)
    right_side = ax[0,2].spines["right"]
    right_side.set_visible(False)
    top = ax[0,2].spines["top"]
    top.set_visible(False)
    # ax[0,2].legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax[0,2].set_title('Available capacity by technology'.format(S), fontsize=8)
    ax[0,2].set_xlabel('Year',fontsize =8)
    # ax[0,2].set_ylim([0,5])
    ax[0,2].tick_params(axis='both', which='major', labelsize=8)
    plt.ylim(0,1300)

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    ax[1,2].set_prop_cycle(material_cycler)
    ax[1,2].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    # ax[1,2].legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax[1,2].set_ylabel('Material weight [kt]',fontsize =8)
    right_side = ax[1,2].spines["right"]
    right_side.set_visible(False)
    top = ax[1,2].spines["top"]
    top.set_visible(False)
    ax[1,2].set_title('Material demand'.format(S), fontsize=8)
    ax[1,2].set_xlabel('Year',fontsize =8)
    ax[1,2].tick_params(axis='both', which='major', labelsize=8)
    ax[1,2].set_ylim(0,3000)
        
    ## Plot second EV penetration scenario
    custom_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu'
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    ax[2,0].set_prop_cycle(custom_cycler)
    ax[2,0].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax[2,0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax[2,0].set_ylabel('Capacity [GWh]',fontsize =8)
    right_side = ax[2,0].spines["right"]
    right_side.set_visible(False)
    top = ax[2,0].spines["top"]
    top.set_visible(False)
    # ax[0,0].legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax[2,0].set_title('Available capacity by technology'.format(S), fontsize=8)
    ax[2,0].set_xlabel('Year',fontsize =8)
    ax[2,0].tick_params(axis='both', which='major', labelsize=8)
    plt.ylim(0,1300)
    material_cycler = cycler(color=sns.color_palette('Paired', 6))

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    ax[3,0].set_prop_cycle(material_cycler)
    ax[3,0].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    # ax[1,0].legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax[3,0].set_ylabel('Material weight [kt]',fontsize =8)
    right_side = ax[3,0].spines["right"]
    right_side.set_visible(False)
    top = ax[3,0].spines["top"]
    top.set_visible(False)
    ax[3,0].set_title('Material demand'.format(S), fontsize=8)
    ax[3,0].set_xlabel('Year',fontsize =8)
    ax[3,0].tick_params(axis='both', which='major', labelsize=8)
    ax[3,0].set_ylim(0,3000)
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 3 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    ax[2,1].set_prop_cycle(custom_cycler)
    ax[2,1].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax[2,1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax[2,1].set_ylabel('Capacity [GWh]',fontsize =8)
    right_side = ax[2,1].spines["right"]
    right_side.set_visible(False)
    top = ax[2,1].spines["top"]
    top.set_visible(False)
    # ax[0,1].legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax[2,1].set_title('Available capacity by technology'.format(S), fontsize=8)
    ax[2,1].set_xlabel('Year',fontsize =8)
    ax[2,1].tick_params(axis='both', which='major', labelsize=8)
    plt.ylim(0,1300)
    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    ax[3,1].set_prop_cycle(material_cycler)
    ax[3,1].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    # ax[1,1].legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax[3,1].set_ylabel('Material weight [kt]',fontsize =8)
    right_side = ax[3,1].spines["right"]
    right_side.set_visible(False)
    top = ax[3,1].spines["top"]
    top.set_visible(False)
    ax[3,1].set_title('Material demand'.format(S), fontsize=8)
    ax[3,1].set_xlabel('Year',fontsize =8)
    ax[3,1].tick_params(axis='both', which='major', labelsize=8)
    ax[3,1].set_ylim(0,3000)
    
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 4 # NCX, LFP, Next_Gen, Roskill
    R = 2 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, V2G mandate, No V2G, early
    e = 3 # Low, medium, high, CP4All
    ax[2,2].set_prop_cycle(custom_cycler)
    ax[2,2].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,R,v,e,55::], \
                    MaTrace_System.StockDict['C_5_SLB'].Values[z,s,a,R,v,e,55::],\
                        MaTrace_System.StockDict['C_5_NSB'].Values[z,s,a,R,v,e,55::]])
    ax[2,2].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[e,55::], 'k')
    ax[2,2].set_ylabel('Capacity [GWh]',fontsize =8)
    right_side = ax[2,2].spines["right"]
    right_side.set_visible(False)
    top = ax[2,2].spines["top"]
    top.set_visible(False)
    # ax[0,2].legend(['Storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax[2,2].set_title('Available capacity by technology'.format(S), fontsize=8)
    ax[2,2].set_xlabel('Year',fontsize =8)
    # ax[0,2].set_ylim([0,5])
    ax[2,2].tick_params(axis='both', which='major', labelsize=8)
    plt.ylim(0,1300)

    # Resource figure for this scenario
    h = 1 # Direct recycling, hydrometallurgical, pyrometallurgical
    ax[3,2].set_prop_cycle(material_cycler)
    ax[3,2].stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:]),\
                    np.einsum('bmt->t', MaTrace_System.FlowDict['E_6_1'].Values[z,s,a,R,v,e,:,:,h,55:]))
    # ax[1,2].legend(['Primary materials', 'Recycled materials'], loc='upper left',prop={'size':15})
    ax[3,2].set_ylabel('Material weight [kt]',fontsize =8)
    right_side = ax[3,2].spines["right"]
    right_side.set_visible(False)
    top = ax[3,2].spines["top"]
    top.set_visible(False)
    ax[3,2].set_title('Material demand'.format(S), fontsize=8)
    ax[3,2].set_xlabel('Year',fontsize =8)
    ax[3,2].tick_params(axis='both', which='major', labelsize=8)
    ax[3,2].set_ylim(0,3000)
    plt.savefig(os.path.join(os.getcwd(), 'results/Manuscript/resource_multi'))
# %%
def plot_material_security():
    from cycler import cycler
    import seaborn as sns
    custom_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu'
    z=0
    h=1 # Hydrometallurgical efficiencies
    a=4 # Faraday chemistries
    e=3 # Low demand
    width = 0.35
    labels = ['LFP reused, \n no V2G', 'All reused,\n no V2G', 'No reuse,\n no V2G', \
        'LFP reused,\n mid V2G', 'All reused,\n mid V2G', 'No reuse,\n mid V2G',\
            'LFP reused,\n high V2G', 'All reused,\n high V2G', 'No reuse,\n high V2G',]
    x = np.arange(len(labels))  # the label locations
    fig, ax = plt.subplots(figsize=(11,10))
    ax.bar(x - width/2, [np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,0,4,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,2,4,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,1,4,e,:,:,h,:]),\
                # mid V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,0,1,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,2,1,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,1,1,e,:,:,h,:]),\
                #High V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,0,3,e,:,:,h,:]), \
            np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,2,3,e,:,:,h,:]),\
                np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,1,a,1,3,e,:,:,h,:])], width, label='Primary')
    ax.bar(x + width/2, [np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,0,4,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,2,4,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,1,4,e,:,:,h,:]),\
                # mid V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,0,1,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,2,1,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,1,1,e,:,:,h,:]),\
                #High V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,0,3,e,:,:,h,:]), \
            np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,2,3,e,:,:,h,:]),\
                np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,1,a,1,3,e,:,:,h,:])], width, label='Secondary')

    # Add some text for labels, title and custom x-axis tick labels, etc.
    ax.set_ylabel('Material use [kt]', fontsize=14)
    ax.set_title('Resource use for fast EV penetration, high demand', fontsize=16)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12)
    ax.legend(fontsize=14)
    fig.tight_layout()
    plt.savefig(os.path.join(os.getcwd(), 'results/Manuscript/material_security_fastEV'))
    
    width = 0.35
    labels = ['LFP reused, \n no V2G', 'All reused,\n no V2G', 'No reuse,\n no V2G', \
        'LFP reused,\n mid V2G', 'All reused,\n mid V2G', 'No reuse,\n mid V2G',\
            'LFP reused,\n high V2G', 'All reused,\n high V2G', 'No reuse,\n high V2G',]
    x = np.arange(len(labels))  # the label locations
    fig, ax = plt.subplots(figsize=(11,10))
    ax.bar(x - width/2, [np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,0,4,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,2,4,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,1,4,e,:,:,h,:]),\
                # mid V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,0,1,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,2,1,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,1,1,e,:,:,h,:]),\
                #High V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,0,3,e,:,:,h,:]), \
            np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,2,3,e,:,:,h,:]),\
                np.einsum('bmt->', MaTrace_System.FlowDict['E_0_1'].Values[z,0,a,1,3,e,:,:,h,:])], width, label='Primary')
    ax.bar(x + width/2, [np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,0,4,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,2,4,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,1,4,e,:,:,h,:]),\
                # mid V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,0,1,e,:,:,h,:]), \
        np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,2,1,e,:,:,h,:]),\
            np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,1,1,e,:,:,h,:]),\
                #High V2G scenarios
                np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,0,3,e,:,:,h,:]), \
            np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,2,3,e,:,:,h,:]),\
                np.einsum('bmt->', MaTrace_System.FlowDict['E_6_1'].Values[z,0,a,1,3,e,:,:,h,:])], width, label='Secondary')

    # Add some text for labels, title and custom x-axis tick labels, etc.
    ax.set_ylabel('Material use [kt]', fontsize=14)
    ax.set_title('Resource use for slow EV penetration, high demand', fontsize=16)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12)
    ax.legend(fontsize=14)
    fig.tight_layout()
    plt.savefig(os.path.join(os.getcwd(), 'results/Manuscript/material_security_slowEV'))
# %%
def plot_P_Anna():
    from cycler import cycler
    import seaborn as sns
    scen_cycler = (cycler(color=['r','g', 'b']) *
            cycler(linestyle=['-','--','-.',':'])) 
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(scen_cycler)
    legend = []
    z=1
    for S in range(NS):
        for a in range(Na):
            ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], np.einsum('sbt->t',MaTrace_System.FlowDict['E_1_2'].Values[z,S,a,:,:,2,55::]))
            ax.set_ylabel('Material weight [kt]',fontsize =18)
            right_side = ax.spines["right"]
            right_side.set_visible(False)
            top = ax.spines["top"]
            top.set_visible(False)
            ax.set_title('Material demand'.format(S), fontsize=20)
            ax.set_xlabel('Year',fontsize =16)
            ax.tick_params(axis='both', which='major', labelsize=18)
            legend.append(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[S]+' '+IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items[a])
            ax.legend(legend, loc='upper left',prop={'size':15})
            #ax.text(2045, np.einsum('sb->',MaTrace_System.FlowDict['E_1_2'].Values[z,S,a,:,:,2,-1]),IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[S]+' '+IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items[a])
# %%
