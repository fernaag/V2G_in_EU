# %% 
# Load a local copy of the current ODYM branch:
from asyncio import new_event_loop
# from curses.panel import bottom_panel
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
xlrd.xlsx.Element_has_iter = True

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
# Model_Configfile     = pd.read_excel(os.path.join(DataPath, ProjectSpecs_ConFile), engine = 'openpyxl')
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
                                                             Indices = 'g,s,c', #t=time, h=units
                                                             Values = np.load(os.getcwd()+'/data/scenario_data/vehicleSize_motorEnergy_passengerCars.npy')[:,:,:], # in %
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
MaTrace_System.FlowDict['C_1_6'] =  msc.Flow(Name = 'New LIBs for stationary storage ', P_Start = 1, P_End = 6,
                                            Indices = 'z,S,a,R,v,E,b,t', Values=None) # Only in terms of capacity
MaTrace_System.FlowDict['C_6_7'] =  msc.Flow(Name = 'New LIBs for stationary storage outflows', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,v,E,b,t', Values=None) # Only in terms of capacity
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
MaTrace_System.StockDict['B_3_V2G']   = msc.Stock(Name = 'V2G ready LIBs in EV in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,s,b,t', Values=None)
MaTrace_System.StockDict['B_C_3_V2G']   = msc.Stock(Name = 'V2G ready LIBs in-use stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,s,b,t,c', Values=None)
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
                                            Indices = 'z,S,a,R,v,E,b,e,h,t', Values=None)
MaTrace_System.FlowDict['E_1_2'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 1, P_End = 2,
                                            Indices = 'z,S,a,s,b,e,t', Values=None)
MaTrace_System.FlowDict['E_2_3'] = msc.Flow(Name = 'Batteries from battery manufacturer to vehicle producer', P_Start = 2, P_End = 3,
                                            Indices = 'z,S,a,s,b,e,t', Values=None)
MaTrace_System.FlowDict['E_3_4'] = msc.Flow(Name = 'Outflows from use phase to ELV collection and dismantling', P_Start = 3, P_End = 4,
                                            Indices = 'z,S,a,b,e,t', Values=None)
MaTrace_System.FlowDict['E_4_5'] = msc.Flow(Name = 'Used LIBs for health assessment and dismantling', P_Start = 4, P_End = 5,
                                            Indices = 'z,S,a,b,e,t', Values=None)
MaTrace_System.FlowDict['E_5_6'] = msc.Flow(Name = 'Used LIBs as second life ', P_Start = 5, P_End = 6,
                                            Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.FlowDict['E_5_8'] = msc.Flow(Name = 'Spent LIBs directly to recycling', P_Start = 5, P_End = 8,
                                            Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.FlowDict['E_6_7'] = msc.Flow(Name = 'Spent LIBs after second life to ELB collector', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,v,E,b,e,t', Values=None)
MaTrace_System.FlowDict['E_1_6'] = msc.Flow(Name = 'Spent LIBs after second life to ELB collector', P_Start = 6, P_End = 7,
                                            Indices = 'z,S,a,R,v,E,b,e,t', Values=None)
MaTrace_System.FlowDict['E_7_8'] = msc.Flow(Name = 'Spent LIBs after second life to to recycling', P_Start = 7, P_End = 8,
                                            Indices = 'z,S,a,R,b,e,t', Values=None)
MaTrace_System.FlowDict['E_8_1'] = msc.Flow(Name = 'Recycled materials materials for battery production', P_Start = 8, P_End = 1,
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
                                              Indices = 'z,S,a,v,g,t', Values=None)
MaTrace_System.StockDict['Con_3']   = msc.Stock(Name = 'Capacity of share of V2G-ready EV stock connected to the grid', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,t', Values=None)
MaTrace_System.StockDict['Pcon_3']   = msc.Stock(Name = 'Power of share of V2G-ready EV stock connected to the grid', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,t', Values=None)
MaTrace_System.StockDict['C_6_SLB']   = msc.Stock(Name = 'Capacity of SLBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,t', Values=None)
MaTrace_System.StockDict['C_6_NSB']   = msc.Stock(Name = 'Capacity of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,E,b,t', Values=None)
MaTrace_System.StockDict['C_6_NSB_tc']   = msc.Stock(Name = 'Capacity of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,E,b,t,c', Values=None)
MaTrace_System.StockDict['Pow_3']   = msc.Stock(Name = 'Total power of V2G-ready EV stock', P_Res = 3, Type = 0,
                                              Indices = 'z,S,a,v,g,t', Values=None)
MaTrace_System.StockDict['Pow_6_SLB']   = msc.Stock(Name = 'Power of SLBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,g,t', Values=None)
MaTrace_System.StockDict['Pow_6_NSB']   = msc.Stock(Name = 'Power of NSBs', P_Res = 6, Type = 0,
                                              Indices = 'z,S,a,R,v,t', Values=None)

MaTrace_System.Initialize_FlowValues()  # Assign empty arrays to flows according to dimensions.
MaTrace_System.Initialize_StockValues() # Assign empty arrays to flows according to dimensions.

### Define lifetimes to be used in the model
'''
Since we are interested in the reuse of batteries, it is important that we understand the technical
limitations of the batteries as a good themselves, rather than batteries for transport. 
The battery lifetime in our case is defined to reflect the amount of time a battery will be
technically functional for the intended purpose, while the vehicle lifetime will relate to the limitations
of the vehicles themselves. Thus, we can assume a lifetime of the battery that is similar than the
conventional warranty of 10 years and use a vehicle lifetime that exceeds the lifetime of ICEs, 
as EVs have less moving and degrading parts. This would be rather conservative estimations and I think that
batteries have been incereasingly shown to last significantly longer than the warranty suggest so we could 
also up the value of the lifetime at some point. 

We also define a delay tau_cm to define the share of batteries that can be reused. This can be 
changed depending on the conditions, but a minimum remaining lifetime of 3 years seems like a reasonable
amount of time considering that SLBs could potentially be relatively cheap since they are considered 
waste, or in some business models are actually still the property of the OEMs. 

--> I'm no longer sure about this approach, since in theory batteries that are no longer good for transportation 
could still be useful for stationary appplications. We could choose a smaller tau like 1 year which really just 
excludes broken batteries and allows for all others to be theoretically useful. Then we can combine that with 
the reuse scenarios to prioritize other chemistries and so on. 
'''
lt_bat = np.array([15])
sd_bat = np.array([4])

lt_car = np.array([15])
sd_car = np.array([5])
# Define minimum amount of useful time
tau_bat = 5
# Define SLB model
Model_slb                                                       = pcm.ProductComponentModel(t = range(0,Nt),  lt_cm = {'Type': 'Normal', 'Mean': lt_bat, 'StdDev': sd_bat}, tau_cm=tau_bat)
# Compute the survival curve of the batteries with the additional lenght for the last tau years
'''
Define the SLB model in advance. We do not compute everything using the dsm as it only takes i as input
and takes too long to compute. Instead, we define the functions ourselves using the sf computed with dsm. 
'''
lt_slb                               = np.array([5]) # We could have different lifetimes for the different chemistries
sd_slb                               = np.array([2]) 
slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb})
slb_model.compute_sf()


'''
I implemented now already all scenarios, but it takes about a  minute to compute. So for debugging it 
makes sense to delete the nested for loops and just use:
z = 1 # BAU stock scenario
g = 1 # BEVs
S = 1 # Sustainable development scenario
'''
# %% 
print('Running model')
# z=1 # Only working with one stock scenario for the moment
for z in range(Nz):
    for g in range(0,Ng):
        for S in range(NS):
            # In this case we assume that the product and component have the same lifetimes and set the delay as 3 years for both goods
            Model                                                     = pcm.ProductComponentModel(t = range(0,Nt), s_pr = MaTrace_System.ParameterDict['Vehicle_stock'].Values[z,:]/1000, lt_pr = {'Type': 'Normal', 'Mean': lt_car, 'StdDev': sd_car }, \
                lt_cm = {'Type': 'Normal', 'Mean': lt_bat, 'StdDev': sd_bat}, tau_cm = tau_bat)
            Model.case_1()
            # Vehicles layer
            MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:]           = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:] ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_pr.copy()))
            MaTrace_System.StockDict['S_3'].Values[z,S,g,:,:]               = np.einsum('stc->st', MaTrace_System.StockDict['S_C_3'].Values[z,S,g,:,:,:])
            MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:,:]              = np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:],np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_pr.copy()))
            MaTrace_System.FlowDict['V_3_4'].Values[z,S,g,:,:,:]            = np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:],np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_pr.copy()))

            ###  LIBs layer, we calculate the stocks anew but this time via the battery dynamics S_C_bat
            MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:]       = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:] \
                ,np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.sc_cm.copy())))
            MaTrace_System.StockDict['B_3'].Values[z,S,:,g,:,:,:]           = np.einsum('asbtc->asbt', MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:])
            ### Calculate share of stock with V2G
            MaTrace_System.StockDict['B_C_3_V2G'].Values[z,S,:,:,g,:,:,:,:]     = np.einsum('vc,asbtc->avsbtc',MaTrace_System.ParameterDict['V2G_rate'].Values[:,g,:], MaTrace_System.StockDict['B_C_3'].Values[z,S,:,g,:,:,:,:])
            MaTrace_System.StockDict['B_3_V2G'].Values[z,S,:,:,g,:,:,:]         = np.einsum('avsbtc->avsbt', MaTrace_System.StockDict['B_C_3_V2G'].Values[z,S,:,:,g,:,:,:,:])
            # Calculating battery inflow in the vehicles
            MaTrace_System.FlowDict['B_2_3'].Values[z,S,:,g,:,:,:]          = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , MaTrace_System.FlowDict['V_2_3'].Values[z,S,g,:,:])
            # Calculating batteryy demand to battery manufacturer including reuse and replacements
            #       Use Model.case_3() instead. This considers two different lifetimes, but replacements and reuse are not allowed.
            #       If we keep this definition, we need to add two additional flows B_1_3 and B_4_3
            MaTrace_System.FlowDict['B_1_2'].Values[z,S,:,g,:,:,:]            = np.einsum('abt,st->asbt', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,c->sc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:], \
                np.einsum('c,c->c', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:],Model.i_cm.copy())))
            # Calculating the outflows based on the battery demand. Here again, this flow will be larger than the number of vehicles due to battery replacements, if allowed.
            # At the moment: LIB flows = EV flows
            MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]        = np.einsum('abc,stc->asbtc', MaTrace_System.ParameterDict['Battery_chemistry_shares'].Values[:,g,:,:] , np.einsum('sc,tc->stc', MaTrace_System.ParameterDict['Segment_shares'].Values[g,:,:], \
                np.einsum('c,tc->tc', MaTrace_System.ParameterDict['Drive_train_shares'].Values[S,g,:] , Model.oc_cm.copy())))
            MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,:,:]      = MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,g,:,:,:,:]
            '''
            We calculate the flows of batteries into reuse. Strictly speaking, only the modules are reused and the casing and other components
            go directly into recycling. However, since we are only interested in the materials in the battery cells, this does not play a role. 
            
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
                        MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,t,c]) # The last term will define the share of batteries reused, while the reuse parameter defines which chemistries, if any, are prioritized
                    # Calculate outflows using the battery pdf: Consider inflow of new batteries here also
            '''
            We will treat the new batteries and second life batteries as separate flows in the model, as the NBS flows are driven by the energy layer. 
            The flows of SLBs are established first in this section and NSB calculated separately below. 

            Since the batteries are moving from being used in transport to being used in stationary storage, the "lifetime" is no longer the same. 
            In transportation, we define the lifetime to be the time that the battery is still useful for that purpose, which is widely considered
            to be until it reaches 80% of its initial capacity. The distribution of the lifetime helps us account for batteries that are more 
            intensely used than others, but by the time of outflow they should all have more or less the same capacity of around 80%. 

            Therefore, the remaining second life can be approximated with a normal distribution that would have an initial capacity of 80% and would
            follow its own degradation curve.  
            '''
            # This was the old way of computing the model that did not seem to be working properly
            # # Calculate the stock: inflow driven model
            # MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,:,:]       = np.einsum('aRsbc,tc->aRsbtc', np.einsum('aRsbtc->aRsbt', MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,g,:,:,:,:]), slb_model.sf)
            # # Calculate outflows
            # MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,g,:,:,1::,:]          = -1 * np.diff(MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,:,:], n=1, axis=4) # difference of older cohorts over time
            # # Allow outflows in the first year
            # for t in range(Nt):
            #     MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,g,:,:,t,t]        = np.einsum('aRsbc->aRsb', MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,g,:,:,t,:]) - MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,t,t]
            # # Calculate total stock
            # MaTrace_System.StockDict['B_6_SLB'].Values[z,S,:,:,g,:,:,:]             = np.einsum('aRsbtc->aRsbt', MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,:,:]) 
            # # Calculate amount of battery parts to recycling after reuse TODO: Add NSB flow here
            # MaTrace_System.FlowDict['B_7_8'].Values[z,S,:,:,g,:,:,:,:]                      = MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,g,:,:,:,:]
            # # Calculate battery parts going directly to recycling: Total outflows minus reuse
            # for R in range(NR):
            #     MaTrace_System.FlowDict['B_5_8'].Values[z,S,:,R,g,:,:,:,:]                  =  MaTrace_System.FlowDict['B_4_5'].Values[z,S,:,g,:,:,:,:] \
            #             - MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,R,g,:,:,:,:]

# %%
# SLB model     
inflows                             = np.zeros((Nz,NS, Na, NR, Nb, Nt))
# Reset cohort information for SLB model
inflows = np.einsum('zSaRgsbtc->zSaRgsbt',MaTrace_System.FlowDict['B_5_6'].Values[:,:,:,:,:,:,:,:,:])
for z in range(Nz):
    for S in range(NS):
        for a in range(Na):
            for R in range(NR):
                for g in range(Ng):
                    for s in range(Ns):
                        for b in range(Nb):
                            slb_model                        = dsm.DynamicStockModel(t=range(0,Nt), lt={'Type': 'Normal', 'Mean': lt_slb, 'StdDev': sd_slb}, i=inflows[z,S,a,R,g,s,b,:])
                            slb_model.compute_s_c_inflow_driven()
                            slb_model.compute_o_c_from_s_c()
                            slb_model.compute_stock_total()
                            MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,a,R,g,s,b,:,:] = slb_model.s_c.copy()
                            MaTrace_System.FlowDict['B_6_7'].Values[z,S,a,R,g,s,b,:,:] = slb_model.o_c.copy()


'''
Now we define the energy layer, where we need to calculate the capacity in the fleet as a whole, 
the capacity available for V2G, and the capacity available from stationary storage. Once this
is calculated, we can compare that to the total demand and compute the necessary additional
stationary storagr (if any) to satisfy that demand. then the ourflows after stationary storage 
need to be calculated using a model for that as well. 
'''
# %%
print('Calculating energy layer')
for z in range(Nz):
    for g in range(0,Ng):
        for S in range(NS): 
            # TODO: Add plug and V2G ratio for the correct calculation of the available capacity. At the moment I just multiply with 0.25 (0.5 V2G available capacity and 0.5 plug ratio)
            MaTrace_System.StockDict['C_3'].Values[z,S,:,:,g,:]         = np.einsum('btc,avbtc->avt', MaTrace_System.ParameterDict['Degradation_fleet'].Values[:,:,:], \
                np.einsum('avsbtc, sc->avbtc', MaTrace_System.StockDict['B_C_3_V2G'].Values[z,S,:,:,g,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[g,:,:])) *0.25
            # Calculate corresponding power
            MaTrace_System.StockDict['Pow_3'].Values[z,S,:,:,g,:]       = MaTrace_System.StockDict['C_3'].Values[z,S,:,:,g,:] *0.25/ 8 # TODO: Define this factor as a parameter
            # Calculate capacities for second life batteries
            '''
            For now I assume that the SLBs are not affected by the V2G scenario. As it is now, we have one scenario to define the reuse
            flows and one scenario to define the V2G penetration. I think that keeping them separately helps us have flexibility in 
            the model and explore different combinations. @Dirk: Do you agree with this?

            We use the capacity for the fleet, since it is the fleet batteries that are reused. For the new stationary storage, we 
            will need to introduce an additional parameter for the capacity and probably also chemistry & degradation. 
            '''
            MaTrace_System.StockDict['C_6_SLB'].Values[z,S,:,:,g,:]       = np.einsum('btc,aRbtc->aRt', MaTrace_System.ParameterDict['Degradation_slb'].Values[:,:,:],\
                np.einsum('aRsbtc, sc->aRbtc', MaTrace_System.StockDict['B_C_6_SLB'].Values[z,S,:,:,g,:,:,:,:], MaTrace_System.ParameterDict['Capacity'].Values[g,:,:]))
            # Calculate corresponding capacity
            MaTrace_System.StockDict['Pow_6_SLB'].Values[z,S,:,:,g,:]     = MaTrace_System.StockDict['C_6_SLB'].Values[z,S,:,:,g,:] / 6 # TODO: Define this factor as a parameter
# %%
'''
Knowing the V2G and SLB available capacity, we can calculate the demand for new batteries. 
We can define a degradation curve that is less steep than the one on EV batteries
since the requirements in this application are lower. This in turn means a longer lifetime. 

For now I assume all NSB are LFP since I don't have material data on teh other chemistries yet.
'''
# TODO: Add material content in terms of capacity for NSB
# TODO: Create new degradation curves for these batteries
Model_nsb = pcm.ProductComponentModel(t = range(0,Nt),  lt_pr = {'Type': 'Normal', 'Mean': np.array([16]), 'StdDev': np.array([4])})
Model_nsb.compute_sf_pr()
for z in range(Nz):
    for S in range(NS):
        for a in range(Na):
            for E in range(NE):
                for v in range(Nv):
                    for R in range(NR):
                        for t in range(1,Nt):
                        # FIXME: For the moment I assume all new batteries are LFP, which is index 2. Inflows equal the gap to satisfy the energy storage needs
                        # FIXME: Need to add the degradation and adjust this in the material demand
                                if MaTrace_System.ParameterDict['Storage_demand'].Values[E,t] -  MaTrace_System.StockDict['C_3'].Values[z,S,a,v,:,t].sum(axis=0) \
                                    - MaTrace_System.StockDict['C_6_SLB'].Values[z,S,a,R,:,t].sum(axis=0) - MaTrace_System.StockDict['C_6_NSB_tc'].Values[z,S,a,R,v,E,2,t,:].sum(axis=0) >0:
                                     MaTrace_System.FlowDict['C_1_6'].Values[z,S,a,R,v,E,2,t] = MaTrace_System.ParameterDict['Storage_demand'].Values[E,t] -  MaTrace_System.StockDict['C_3'].Values[z,S,a,v,:,t].sum(axis=0) \
                                        - MaTrace_System.StockDict['C_6_SLB'].Values[z,S,a,R,:,t].sum(axis=0) - MaTrace_System.StockDict['C_6_NSB_tc'].Values[z,S,a,R,v,E,2,t,:].sum(axis=0)
                                     MaTrace_System.StockDict['C_6_NSB_tc'].Values[z,S,a,R,v,E,2,t::,t] = MaTrace_System.FlowDict['C_1_6'].Values[z,S,a,R,v,E,2,t]*  Model_nsb.sf_pr[t::,t]
                                # Calculate the stock based on those inflows and correct value that will be calculated below
                                else: 
                                    MaTrace_System.FlowDict['C_1_6'].Values[z,S,a,R,v,E,2,t] = 0
                                    MaTrace_System.StockDict['C_6_NSB_tc'].Values[z,S,a,R,v,E,2,t::,t] = MaTrace_System.FlowDict['C_1_6'].Values[z,S,a,R,v,E,2,t]*  Model_nsb.sf_pr[t::,t]
                        MaTrace_System.StockDict['C_6_NSB'].Values[z,S,a,R,v,E,2,:] = MaTrace_System.StockDict['C_6_NSB_tc'].Values[z,S,a,R,v,E,2,:,:].sum(axis=1)
                        MaTrace_System.FlowDict['C_6_7'].Values[z,S,a,R,v,E,2,1:]            = np.diff(MaTrace_System.StockDict['C_6_NSB'].Values[z,S,a,R,v,E,2,:]) - MaTrace_System.FlowDict['C_1_6'].Values[z,S,a,R,v,E,2,1:]
# %%
'''
Here we calculate the material flows for Ni, Co, Li, P, C, Mn, which are materials exclusively in modules.
Since we are only interested in the cell materials, we define the material content based on the size of the battery 
independently of whether that battery has been dismantled or not (cell material content does not change in this process).
See material_content.ipynb for a detailed description and data for the calculations. 

We aggregate the cohorts to have the total flows, as the cohort composition is not interesting in the 
context of materials. 
'''
print('Running element layer')
for z in range(Nz):
    for g in range(0,Ng):
        for S in range(NS): 
            MaTrace_System.StockDict['E_C_3'].Values[z,S,:,:,:,:,:,:]     = np.einsum('gsbe, agsbtc->asbetc', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.StockDict['B_C_3'].Values[z,S,:,:,:,:,:,:])
            MaTrace_System.StockDict['E_3'].Values[z,S,:,:,:,:,:]         = np.einsum('asbetc->asbet', MaTrace_System.StockDict['E_C_3'].Values[z,S,:,:,:,:,:,:])
            # Calculate inflows 
            MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,:,:,:,:]        = np.einsum('gsbe,agsbt->asbet',MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_1_2'].Values[z,S,:,:,:,:,:])
            MaTrace_System.FlowDict['E_2_3'].Values[z,S,:,:,:,:,:]        = MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,:,:,:,:]
            # Calculate outflows
            MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,:,:,:]        = np.einsum('gsbe,agsbtc->abet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_3_4'].Values[z,S,:,:,:,:,:,:])
            MaTrace_System.FlowDict['E_4_5'].Values[z,S,:,:,:,:]        = MaTrace_System.FlowDict['E_3_4'].Values[z,S,:,:,:,:]
            # Calculate flows at second life: Aggregate segments as no longer relevant
            MaTrace_System.FlowDict['E_5_6'].Values[z,S,:,:,:,:,:]        = np.einsum('gsbe,aRgsbtc->aRbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_5_6'].Values[z,S,:,:,:,:,:,:,:])
            for E in range(NE):
                for v in range(Nv):
                    MaTrace_System.FlowDict['E_6_7'].Values[z,S,:,:,v,E,:,:,:]          = np.einsum('gsbe,aRgsbtc->aRbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,:,:,:,:,:]) \
                        + np.einsum('gbe,aRbt->aRbet',MaTrace_System.ParameterDict['Material_content_NSB'].Values[:,:,:], MaTrace_System.FlowDict['C_6_7'].Values[z,S,:,:,v,E,:,:])
            # Calculate material stock? Slows down model and not necessarily insightful
            # Calculate recycling flows
            for R in range(NR):
                MaTrace_System.FlowDict['E_5_8'].Values[z,S,:,R,:,:,:]      = MaTrace_System.FlowDict['E_4_5'].Values[z,S,:,:,:,:] - MaTrace_System.FlowDict['E_5_6'].Values[z,S,:,R,:,:,:]
                MaTrace_System.FlowDict['E_1_6'].Values[z,S,:,R,:,:,:,:,:]      = np.einsum('gbe,avEbt->avEbet',MaTrace_System.ParameterDict['Material_content_NSB'].Values[:,:,:], MaTrace_System.FlowDict['C_1_6'].Values[z,S,:,R,:,:,:,:])
            MaTrace_System.FlowDict['E_7_8'].Values[z,S,:,:,:,:,:]          = np.einsum('gsbe,aRgsbtc->aRbet', MaTrace_System.ParameterDict['Material_content'].Values[:,:,:,:], MaTrace_System.FlowDict['B_6_7'].Values[z,S,:,:,:,:,:,:,:]) 
            # FIXME: Add NSB outflows
            # Calculate recovered materials for different recycling technologies and corresponding promary material demand
            for v in range(Nv):
                for E in range(NE):
                    MaTrace_System.FlowDict['E_8_1'].Values[z,S,:,:,v,E,:,:,:,:]        = np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], MaTrace_System.FlowDict['E_7_8'].Values[z,S,:,:,:,:,:]) +\
                        np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], MaTrace_System.FlowDict['E_5_8'].Values[z,S,:,:,:,:,:]) \
                            + np.einsum('eh,aRbet->aRbeht', MaTrace_System.ParameterDict['Recycling_efficiency'].Values[:,:], np.einsum('gbe,aRbt->aRbet',MaTrace_System.ParameterDict['Material_content_NSB'].Values[:,:,:], MaTrace_System.FlowDict['C_6_7'].Values[z,S,:,:,v,E,:,:]))
            # Calculate demand for primary materials
            for R in range(NR):
                for h in range(Nh):
                    for v in range(Nv):
                        for E in range(NE):
                            MaTrace_System.FlowDict['E_0_1'].Values[z,S,:,R,v,E,:,:,h,:]    = np.einsum('asbet->abet', MaTrace_System.FlowDict['E_1_2'].Values[z,S,:,:,:,:,:]) - MaTrace_System.FlowDict['E_8_1'].Values[z,S,:,R,v,E,:,:,h,:] + MaTrace_System.FlowDict['E_1_6'].Values[z,S,:,R,v,E,:,:,:]#
                    
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

'''
The following is the code for the figures we show Francois 16.09.21
'''
# %% 
def plot_capacity_scenarios():
    from cycler import cycler
    import seaborn as sns
    scen_cycler = (cycler(color=['orangered', 'royalblue']) *
          cycler(linestyle=['-','--',':']))    
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 3 # NCX, LFP, Next_Gen, Roskill
    R = 2 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g
    e = 2 # Low, medium, high
    fig, ax = plt.subplots(1,2,figsize=(20,7))
    ax[0].set_prop_cycle(scen_cycler)
    ax[0].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 0,MaTrace_System.ParameterDict['Storage_demand'].Values[0,70::]/1000, color='lightgrey', alpha=0.6)
    ax[0].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[0,70::]/1000, MaTrace_System.ParameterDict['Storage_demand'].Values[1,70::]/1000, color='darkgrey', alpha=0.6)
    ax[0].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[1,70::]/1000, MaTrace_System.ParameterDict['Storage_demand'].Values[2,70::]/1000, color='grey', alpha=0.6)
    
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,0,a,1,:,70::].sum(axis=0)/1000)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,0,a,2,:,70::].sum(axis=0)/1000)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,0,a,3,:,70::].sum(axis=0)/1000)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,1,a,1,:,70::].sum(axis=0)/1000)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,1,a,2,:,70::].sum(axis=0)/1000)
    ax[0].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.StockDict['C_3'].Values[z,1,a,3,:,70::].sum(axis=0)/1000)
    ax[0].set_ylabel('Capacity [TWh]',fontsize =18)
    right_side = ax[0].spines["right"]
    right_side.set_visible(False)
    top = ax[0].spines["top"]
    top.set_visible(False)
    ax[0].legend(['Low storage demand','Medium storage demand','High storage demand', 'V2G low, STEP', 'V2G medium, STEP', 'V2G mandate, STEP', 'V2G low, SD', 'V2G medium, SD', 'V2G mandate, SD'], loc='upper left',prop={'size':15})
    ax[0].set_title('a) Available V2G capacity by scenario'.format(S), fontsize=20)
    ax[0].set_xlabel('Year',fontsize =16)
    ax[0].tick_params(axis='both', which='major', labelsize=18)
    ax[0].set_ylim(0,4)
    ax[0].set_xlim(2020,2050)
    ax[0].grid()

    from cycler import cycler
    import seaborn as sns
    scen_cycler = (cycler(color=['orangered','royalblue']) *
          cycler(linestyle=['-','--'])) 
    z = 1 # Low, medium, high
    s = 0 # Low, medium, high
    a = 3 # NCX, LFP, Next_Gen, Roskill, BNEF, Faraday
    R = 0 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g
    e = 2 # Low, medium, high
    ax[1].set_prop_cycle(scen_cycler)
    ax[1].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 0,MaTrace_System.ParameterDict['Storage_demand'].Values[0,70::]/1000, color='lightgrey', alpha=0.6)
    ax[1].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[0,70::]/1000, MaTrace_System.ParameterDict['Storage_demand'].Values[1,70::]/1000, color='darkgrey', alpha=0.6)
    ax[1].fill_between(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], MaTrace_System.ParameterDict['Storage_demand'].Values[1,70::]/1000, MaTrace_System.ParameterDict['Storage_demand'].Values[2,70::]/1000, color='grey', alpha=0.6)
    
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,0,a,1,:,70::].sum(axis=0)/1000)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,0,a,2,:,70::].sum(axis=0)/1000)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,1,a,1,:,70::].sum(axis=0)/1000)
    ax[1].plot(MaTrace_System.IndexTable['Classification']['Time'].Items[70::], 
                MaTrace_System.StockDict['C_6_SLB'].Values[z,1,a,2,:,70::].sum(axis=0)/1000)
    ax[1].set_ylabel('Capacity [TWh]',fontsize =18)
    right_side = ax[1].spines["right"]
    right_side.set_visible(False)
    top = ax[1].spines["top"]
    top.set_visible(False)
    ax[1].legend(['Low storage demand','Medium storage demand','High storage demand', 'LFP reused - STEP', 'All reused - STEP', 'LFP reused - SD', 'All reused - SD'], loc='upper left',prop={'size':15})
    ax[1].set_title('b) Available SLB capacity by scenario'.format(S), fontsize=20)
    ax[1].set_xlabel('Year',fontsize =16)
    ax[1].tick_params(axis='both', which='major', labelsize=18)
    ax[1].set_xlim(2020,2050)
    ax[1].grid()
    plt.ylim(0,4)
    plt.savefig(os.path.join(os.getcwd(), 'results/Manuscript/capacity_scenarios'), dpi=600)
    
# Call plot_capacity_scenarios()
#plot_capacity_scenarios()

def plot_only_NSB():
    from cycler import cycler
    import seaborn as sns
    custom_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu'
    z = 0 # Low, medium, high
    s = 1 # Low, medium, high
    a = 3 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g
    e = 2 # Low, medium, high
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,v,:,55::].sum(axis=0), \
                    MaTrace_System.StockDict['C_6_SLB'].Values[z,s,a,R,:,55::].sum(axis=0),\
                        MaTrace_System.StockDict['C_6_NSB'].Values[z,s,a,R,v,e,:,55::].sum(axis=0)])
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[0,55::], '--k')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[1,55::], 'xk')
    ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], MaTrace_System.ParameterDict['Storage_demand'].Values[2,55::], 'k')
    ax.set_ylabel('Capacity [GWh]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.legend(['Low storage demand','Medium storage demand','High storage demand', 'V2G', 'SLB', 'New batteries'], loc='upper left',prop={'size':15})
    ax.set_title('Available capacity by technology'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.text(2005, 500, 'Baseline stock and electrification', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 400, 'Ni-rich technology', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 300, 'LFP reused', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    ax.text(2005, 200, 'Low V2G penetration', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
            
    ax.text(2005, 100, 'Medium demand', style='italic',
            bbox={'facecolor': 'red', 'alpha': 0.3, 'pad': 10}, fontsize=15)
    #ax.set_ylim([0,5])
    ax.tick_params(axis='both', which='major', labelsize=18)
    #plt.ylim(0,800)
    material_cycler = cycler(color=['r','g','b','yellow','m','dimgrey', 'indianred', 'yellowgreen', 'cornflowerblue', 'palegoldenrod', 'plum', 'lightgrey']) #'Set2', 'Paired', 'YlGnBu'

    # Resource figure for this scenario
    h = 0 # Direct recycling, hydrometallurgical, pyrometallurgical
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(material_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                    MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0),\
                    MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,:,:,h,55:].sum(axis=0))
    ax.legend(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[:]+['Rec. Li', 'Rec. Graphite', 'Rec. P', 'Rec. Mn', 'Rec. Co', 'Rec. Ni'], loc='upper left',prop={'size':15})
    ax.set_ylabel('Material weight [kt]',fontsize =18)
    right_side = ax.spines["right"]
    right_side.set_visible(False)
    top = ax.spines["top"]
    top.set_visible(False)
    ax.set_title('Material demand'.format(S), fontsize=20)
    ax.set_xlabel('Year',fontsize =16)
    ax.tick_params(axis='both', which='major', labelsize=18)
    plt.ylim(0,4500)

def plot_energy_resource_graphs():
    from cycler import cycler
    import seaborn as sns
    custom_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu'
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    a = 3 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, v2g mandate, no v2g, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,v,:,55::].sum(axis=0), \
                    MaTrace_System.StockDict['C_6_SLB'].Values[z,s,a,R,:,55::].sum(axis=0),\
                        MaTrace_System.StockDict['C_6_NSB'].Values[z,s,a,R,v,e,:,55::].sum(axis=0)])
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
                    MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0))
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
    s = 1 # Low, medium, high
    a = 3 # NCX, LFP, Next_Gen, Roskill
    R = 1 # LFP reused, no reuse, all reuse
    v = 3 # Low, medium, high, v2g mandate, no v2g, early
    e = 3# Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,v,:,55::].sum(axis=0), \
                    MaTrace_System.StockDict['C_6_SLB'].Values[z,s,a,R,:,55::].sum(axis=0),\
                        MaTrace_System.StockDict['C_6_NSB'].Values[z,s,a,R,v,e,:,55::].sum(axis=0)])
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
                    MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0))
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
    s = 1 # Low, medium, high
    a = 3 # NCX, LFP, Next_Gen, Roskill
    R = 0 # LFP reused, no reuse, all reuse
    v = 4 # Low, medium, high, V2G mandate, No V2G, early
    e = 3 # Low, medium, high, CP4All
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(custom_cycler)
    ax.stackplot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                [MaTrace_System.StockDict['C_3'].Values[z,s,a,v,:,55::].sum(axis=0), \
                    MaTrace_System.StockDict['C_6_SLB'].Values[z,s,a,R,:,55::].sum(axis=0),\
                        MaTrace_System.StockDict['C_6_NSB'].Values[z,s,a,R,v,e,:,55::].sum(axis=0)])
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
    ax.text(2005, 400, 'LFP reused', style='italic',
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
                    MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,:,h,55:].sum(axis=0))
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

def plot_resource_range():
    from cycler import cycler
    import seaborn as sns
    resource_cycler = cycler(color=['slategrey', 'lightsteelblue', 'cornflowerblue', 'royalblue', 'navy', 'k', 'pink','lightcoral', 'indianred', 'r', 'brown', 'maroon']) #'Set2', 'Paired', 'YlGnBu'
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    R = 1 # LFP reused, no reuse, all reuse
    v = 5 # Low, medium, high, V2G mandate, No V2G, early
    e = 0 # Low, medium, high, CP4All
    h = 0 # Direct recycling, hydrometallurgical, pyrometallurgical
    for m in range(Ne):
        fig, ax = plt.subplots(figsize=(8,7))
        ax.set_prop_cycle(resource_cycler)
        ax.set_title('{} demand - {}'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[m], IndexTable.Classification[IndexTable.index.get_loc('Recycling_Process')].Items[h]), fontsize=20)
        for a in range(Na):
            ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                            MaTrace_System.FlowDict['E_0_1'].Values[z,s,a,R,v,e,:,m,h,55:].sum(axis=0) + MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,m,h,55:].sum(axis=0))
            #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
            #                MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,m,h,55:].sum(axis=0))
                            
        ax.legend(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items[:]+ IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items[:], loc='upper left',prop={'size':15})
        ax.set_ylabel('Material weight [kt]',fontsize =18)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.set_xlabel('Year',fontsize =16)
        ax.tick_params(axis='both', which='major', labelsize=18)

def plot_rec_resource_range():
    from cycler import cycler
    import seaborn as sns
    resource_cycler = cycler(color=['pink','lightcoral', 'indianred', 'r', 'brown', 'maroon']) #'Set2', 'Paired', 'YlGnBu'
    z = 1 # Low, medium, high
    s = 1 # Low, medium, high
    R = 1 # LFP reused, no reuse, all reuse
    v = 5 # Low, medium, high, V2G mandate, No V2G, early
    e = 0 # Low, medium, high, CP4All
    h = 0 # Direct recycling, hydrometallurgical, pyrometallurgical
    for m in range(Ne):
        fig, ax = plt.subplots(figsize=(8,7))
        ax.set_prop_cycle(resource_cycler)
        ax.set_title('Recycled {} availability - {}'.format(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items[m], IndexTable.Classification[IndexTable.index.get_loc('Recycling_Process')].Items[h]), fontsize=20)
        for a in range(Na):
            ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
                            MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,m,h,55:].sum(axis=0))
                            
        ax.legend(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items[:], loc='upper left',prop={'size':15})
        ax.set_ylabel('Material weight [kt]',fontsize =18)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.set_xlabel('Year',fontsize =16)
        ax.tick_params(axis='both', which='major', labelsize=18)

def plot_flows():
    from cycler import cycler
    import seaborn as sns
    flows_cycler = cycler(color=sns.color_palette('Accent', 6)) #'Set2', 'Paired', 'YlGnBu', 'Accent'
    z = 1 # Low, medium, high
    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(flows_cycler)
    for s in range(NS):
        ax.set_title('Inflows by scenario'.format(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[s]), fontsize=20)
        ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                            MaTrace_System.FlowDict['V_2_3'].Values[z,s,1,:,65:].sum(axis=0))
            #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
            #                MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,m,h,55:].sum(axis=0))
                            
        ax.legend(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[:], loc='upper left',prop={'size':15})
        ax.set_ylabel('BEV sales [million]',fontsize =18)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.set_xlabel('Year',fontsize =16)
        ax.tick_params(axis='both', which='major', labelsize=18)
        plt.ylim(0,30)

    fig, ax = plt.subplots(figsize=(8,7))
    ax.set_prop_cycle(flows_cycler)
    for s in range(NS):
        ax.set_title('Outflows by scenario'.format(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[s]), fontsize=20)
        ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[65::], 
                            np.einsum('btc->t', MaTrace_System.FlowDict['V_3_4'].Values[z,s,1,:,65:,:]))
            #ax.plot(MaTrace_System.IndexTable['Classification']['Time'].Items[55::], 
            #                MaTrace_System.FlowDict['E_8_1'].Values[z,s,a,R,v,e,:,m,h,55:].sum(axis=0))
                            
        ax.legend(IndexTable.Classification[IndexTable.index.get_loc('EV_penetration_scenario')].Items[:], loc='upper left',prop={'size':15})
        ax.set_ylabel('BEV outflows [million]',fontsize =18)
        right_side = ax.spines["right"]
        right_side.set_visible(False)
        top = ax.spines["top"]
        top.set_visible(False)
        ax.set_xlabel('Year',fontsize =16)
        ax.tick_params(axis='both', which='major', labelsize=18)
        plt.ylim(0,30)

## Exporting P values Anna
def export_P_values():
    results = os.path.join(os.getcwd(), 'results')
    np.save(results+'/arrays/P_demand_primary_EU',np.einsum('SaRbht->SaRht',MaTrace_System.FlowDict['E_0_1'].Values[0,:,:,:,3,0,:,2,:,:]), allow_pickle=True)# 'z,S,a,R,v,E,b,e,h,t'
    np.save(results+'/arrays/P_demand_recycled_EU',np.einsum('SaRbht->SaRht',MaTrace_System.FlowDict['E_8_1'].Values[0,:,:,:,3,0,:,2,:,:]), allow_pickle=True)# 'z,S,a,R,v,E,b,e,h,t'

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
