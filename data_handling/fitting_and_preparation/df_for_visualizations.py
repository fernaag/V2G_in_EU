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
# For Ipython Notebook only
### Preamble

# add ODYM module directory to system path, relative
MainPath = os.path.join('/Users/fernaag/Box/BATMAN/Coding/Global_model', 'odym', 'modules')
sys.path.insert(0, MainPath)

# add ODYM module directory to system path, absolute
sys.path.insert(0, os.path.join(os.getcwd(), 'odym', 'modules'))

# Specify path to dynamic stock model and to datafile, relative
DataPath = os.path.join( 'docs', 'files')

# Specify path to dynamic stock model and to datafile, absolute
DataPath = os.path.join('/Users/fernaag/Box/BATMAN/Coding/Global_model', 'docs', 'Files')

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
Ng = len(IndexTable.Classification[IndexTable.index.get_loc('Good')].Items)
Nr = len(IndexTable.Classification[IndexTable.index.get_loc('Region')].Items)
Ne = len(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items)
Nb = len(IndexTable.Classification[IndexTable.index.get_loc('Battery_Chemistry')].Items)
Nk = len(IndexTable.Classification[IndexTable.index.get_loc('Capacity')].Items)
Np = len(IndexTable.Classification[IndexTable.index.get_loc('Battery_Parts')].Items)
Ns = len(IndexTable.Classification[IndexTable.index.get_loc('Size')].Items)
Nh = len(IndexTable.Classification[IndexTable.index.get_loc('Recycling_Process')].Items)
Nv = len(IndexTable.Classification[IndexTable.index.get_loc('Make')].Items)
NS = len(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items)
Na = len(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items)
Nz = len(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items)
NR = len(IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items)

### Importing model output

inflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_inflow_array.npy') # dims: z,S,r,g,t
outflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_outflow_array.npy') # dims: z,S,r,g,t
stock = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_stock_array.npy') # z,S,r,g,s,t

bat_inflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_inflow_array.npy') # dims: z,S,a,r,b,p,t
bat_outflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_outflow_array.npy') # dims: z,S,a,r,b,p,t
bat_reuse = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_array.npy') # dims: zSaRrbpt
bat_reuse_to_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_to_recycling_array.npy') # dims: zSaRrbpt
bat_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_recycling_array.npy') # zSaRrbpt

mat_inflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_inflow_array.npy') # dims: zSarept
mat_outflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_outflow_array.npy') # dims: z,S,a,r,g,b,p,t
mat_reuse = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_array.npy') # dims: zSaRrbpt
mat_reuse_to_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_to_recycling_array.npy') # dims: zSaRrbpt
mat_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycling_array.npy') # zSaRrbpt
mat_loop = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycled_process_array.npy') # zSaRrbpt
mat_loss = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_losses_array.npy') # zSaRrbpt

### Creating empty dataframes
sp0, sp1, sp2, sp3, sp5 = pd.core.reshape.util.cartesian_product([IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items, IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items, \
    IndexTable.Classification[IndexTable.index.get_loc('Region')].Items, IndexTable.Classification[IndexTable.index.get_loc('Good')].Items, \
        IndexTable.Classification[IndexTable.index.get_loc('Time')].Items])

lp0, lp1, lp2, lp3, lp5 = pd.core.reshape.util.cartesian_product([IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items, IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items, \
    IndexTable.Classification[IndexTable.index.get_loc('Region')].Items, IndexTable.Classification[IndexTable.index.get_loc('Good')].Items, \
        IndexTable.Classification[IndexTable.index.get_loc('Time')].Items])


inflow_df = pd.DataFrame(dict(Stock_Scenarios= lp0, Scenario=lp1, Region= lp2, Good=lp3, Time=lp5))
outflow_df = pd.DataFrame(dict(Stock_Scenarios= lp0, Scenario=lp1, Region= lp2, Good=lp3, Time=lp5))
stock_df = pd.DataFrame(dict(Stock_Scenarios= sp0, Scenario=sp1, Region= sp2, Good=sp3, Time=sp5))

### Adding data to the dataframes
for a,z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
    for b,S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items):
        for c,r in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Region')].Items):
            for d,g in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Good')].Items):
                inflow_df.loc[(inflow_df.Stock_Scenarios == z) & (inflow_df.Scenario == S)& (inflow_df.Region == r)& (inflow_df.Good == g), 'value'] = inflow[a,b,c,d,:]
                outflow_df.loc[(outflow_df.Stock_Scenarios == z) & (outflow_df.Scenario == S)& (outflow_df.Region == r)& (outflow_df.Good == g), 'value'] = outflow[a,b,c,d,:]
                stock_df.loc[(stock_df.Stock_Scenarios == z) & (stock_df.Scenario == S)& (stock_df.Region == r)& (stock_df.Good == g), 'value'] = stock[a,b,c,d,:]

inflow_df.to_pickle('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/model_output/vehicle_layer/inflow_df')
outflow_df.to_pickle('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/model_output/vehicle_layer/outflow_df')
stock_df.to_pickle('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/model_output/vehicle_layer/stock_df')

### Now we do the same for the material content
'''
lp0, lp1, lp2, lp3, lp4, lp5, lp6, lp7 = pd.core.reshape.util.cartesian_product([IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items, \
    IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items, IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items,\
    IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items, \
    IndexTable.Classification[IndexTable.index.get_loc('Region')].Items, IndexTable.Classification[IndexTable.index.get_loc('Element')].Items, \
    IndexTable.Classification[IndexTable.index.get_loc('Battery_Parts')].Items, \
        IndexTable.Classification[IndexTable.index.get_loc('Time')].Items])

recycled_content_df = pd.DataFrame(dict(Stock_scenario= lp0, EV_penetration_scenario=lp1, Battery_chemistry_scenario= lp2, Reuse_scenario=lp3, Region=lp4, Material=lp5,  Battery_part=lp6, Year=lp7))
### Adding data to the dataframe
for a,z in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Stock_Scenarios')].Items):
    for b,S in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Scenario')].Items):
        for c,A in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Chemistry_Scenarios')].Items):
            for d,R in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Reuse_Scenarios')].Items):
                for e,r in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Region')].Items):
                    for f,E in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items):
                        for g,p in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Battery_Parts')].Items):
                            recycled_content_df.loc[(recycled_content_df.Stock_scenario == z) & (recycled_content_df.EV_penetration_scenario == S) & (recycled_content_df.Battery_chemistry_scenario == A) \
                                & (recycled_content_df.Reuse_scenario == R) & (recycled_content_df.Region == r) \
                                & (recycled_content_df.Material == E) & (recycled_content_df.Battery_part == p), 'value'] = mat_loop[a,b,c,d,e,f,g,:] / (mat_inflow[a,b,c,d,e,f,g,:] + mat_loop[a,b,c,d,e,f,g,:])

#recycled_content_df.to_pickle('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/model_output/material_layer/recycled_content_df')
global_rec_cont = recycled_content_df.dropna()
global_rec_cont.to_excel('/Users/fernaag/Box/BATMAN/Data/Database/data/03_scenario_data/global_model/model_output/material_layer/recycled_content.xlsx')
'''

### Graph values for Equinor
rec_content = np.load('/Users/fernaag/Box/BATMAN/Partners/Equinor/average_recycled_content.npy')
dem1 = np.load('/Users/fernaag/Box/BATMAN/Partners/Equinor/material_demand_NCX.npy')
dem2 = np.load('/Users/fernaag/Box/BATMAN/Partners/Equinor/material_demand_LFP.npy')

mp0, mp1 = pd.core.reshape.util.cartesian_product([IndexTable.Classification[IndexTable.index.get_loc('Element')].Items, \
    IndexTable.Classification[IndexTable.index.get_loc('Time')].Items])

recycled_content_df = pd.DataFrame(dict(Material=mp0,  Year=mp1))


for f,E in enumerate(IndexTable.Classification[IndexTable.index.get_loc('Element')].Items):
    recycled_content_df.loc[(recycled_content_df.Material == E) & (recycled_content_df.Year >2019), 'Upper demand'] =dem1[f, :]
    recycled_content_df.loc[(recycled_content_df.Material == E)& (recycled_content_df.Year >2019), 'Lower demand'] =dem2[f, :]
    recycled_content_df.loc[(recycled_content_df.Material == E)& (recycled_content_df.Year >2019), 'Recycled content'] =rec_content[f, :]

recycled_content_df['Stock_scenario'] = 'BAU'
recycled_content_df['EV_penetration_scenario'] = 'Sustainable development'
recycled_content_df['Reuse_scenario'] = 'No reuse'
recycled_content_df['Battery component'] = 'Modules'
recycled_content_df['Region'] = 'Global'
recycled_content_df.dropna(inplace=True)
recycled_content_df.to_excel('/Users/fernaag/Box/BATMAN/Partners/Equinor/plot_data.xlsx')