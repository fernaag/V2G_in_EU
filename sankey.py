
import os
import json
import urllib
import numpy as np

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
results = os.path.join(os.getcwd(), 'results')

inflow = np.load(results+'/arrays/vehicle_inflow_array.npy') # dims: z,S,r,g,s,t
outflow = np.load(results+'/arrays/vehicle_outflow_array.npy') # dims: z,S,r,g,s,t

bat_inflow = np.load(results+'/arrays/battery_inflow_array.npy') # dims: z,S,a,r,b,p,t
bat_outflow = np.load(results+'/arrays/battery_outflow_array.npy') # dims: z,S,a,r,b,p,t
bat_reuse = np.load(results+'/arrays/battery_reuse_array.npy') # dims: zSaRrbpt
bat_reuse_to_rec = np.load(results+'/arrays/battery_reuse_to_recycling_array.npy') # dims: zSaRrbpt
bat_rec = np.load(results+'/arrays/battery_recycling_array.npy') # zSaRrbpt

mat_inflow = np.load(results+'/arrays/material_primary_array.npy') # dims: zSarept
mat_outflow = np.load(results+'/arrays/material_outflow_array.npy') # dims: z,S,a,r,g,b,p,t
mat_reuse = np.load(results+'/arrays/material_reuse_array.npy') # dims: zSaRrbpt
mat_reuse_to_rec = np.load(results+'/arrays/material_reuse_to_recycling_array.npy') # dims: zSaRrbpt
mat_rec = np.load(results+'/arrays/material_recycling_array.npy') # zSaRrbpt
mat_loop = np.load(results+'/arrays/material_recycled_process_array.npy') # zSaRrbpt
#mat_loss = np.load(results+'/arrays/material_losses_array.npy') # zSaRrbpt


app = dash.Dash(__name__)

app.layout = html.Div([
    html.Div([

        html.Div([
            dcc.Graph(id="graph"),
            html.P("Year"),
            dcc.Slider(id='year', min=2010, max=2050, 
                    value=2021, step=1, marks={str(year): str(year) for year in range(1950,2051)}
            )]),
        html.Div([
            html.P("Stock scenario"),
            dcc.Dropdown(
                id='stock_scenario',
                options=[{'label': j, 'value': i} for i,j in enumerate(['Autonomous vehicles', 'Baseline', 'High ownership'])],
                value=1
            )]),
        html.Div([
            html.P("EV penetration scenario"),
            dcc.Dropdown(
                id='ev_scenario',
                options=[{'label': j, 'value': i} for i,j in enumerate(['Stated policies', 'Sustainable development', 'Net Zero'])],
                value=1
            )]),
        html.Div([
            html.P("Battery chemistry scenario"),
            dcc.Dropdown(
                id='chem_scenario',
                options=[{'label': j, 'value': i} for i,j in enumerate(['NCX', 'LFP', 'Next_gen', 'Roskill'])],
                value=0
            )]),
        html.Div([
            html.P("Recycling process"),
            dcc.Dropdown(
                id='recycling_process',
                options=[{'label': j, 'value': i} for i,j in enumerate(['Direct recycling', 'Hydrometallurgycal', 'Pyrometallurgical'])],
                value=0
            )]),
        html.Div([
            html.P("Reuse scenario"),
            dcc.Dropdown(
                id='reuse_scenario',
                options=[{'label': j, 'value': i} for i,j in enumerate(['LFP reused', 'No reuse', 'All reused'])],
                value=0
            )])
  ])])


@app.callback(
    Output("graph", "figure"), 
    Input("year", "value"),
    Input('stock_scenario', 'value'),
    Input('ev_scenario', 'value'),
    Input('chem_scenario', 'value'),
    Input('recycling_process', 'value'),
    Input('reuse_scenario', 'value'))

def display_sankey(year, stock_scenario, ev_scenario, chem_scenario, recycling_process,reuse_scenario):
    year = year
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    reuse_scenario = reuse_scenario
    recycling_process =recycling_process
    ### First we add the vehicle layer
    fig = go.Figure(data=[go.Sankey(
    domain={
            'x': [0, 0.35],
            'y': [0.55, 1],
        },
    node = dict(
      pad = 15,
      thickness = 20,
      line = dict(color = "black", width = 0.5),
      label = ["Vehicle manufacturer", "In use stock", "End of life management"],
      color = "lightsteelblue"
    ),
    link = dict(
      source = [0, 1,  0, 1, 0, 1], # indices correspond to labels, eg A1, A2, A1, B1, ...
      target = [1, 2,  1, 2, 1,2],
      color = ["aliceblue", "aliceblue","mediumseagreen",  "mediumseagreen", "orange","orange"],
      label = ["New ICE", "EOL ICE", "New BEV", "EOL BEV", "New PHEV", "EOL PHEV"], 
      value = [inflow[stock_scenario,ev_scenario,0,year-1950], outflow[stock_scenario,ev_scenario,0,year-1950], inflow[stock_scenario,ev_scenario,1,year-1950], outflow[stock_scenario,ev_scenario,1,year-1950], inflow[stock_scenario,ev_scenario,3,year-1950], outflow[stock_scenario,ev_scenario,3,year-1950]], 
  )), 
  ### Now we add the battery layer
  go.Sankey(domain={
            'x': [0, 0.35],
            'y': [0, 0.5],
        },
    arrangement="snap",
    node = dict(
      pad = 15,
      thickness = 20,
      line = dict(color = "black", width = 0.5),
      label = ["Battery manufacturer", "In use batteries", "End of life batteries", "Reuse", "Recycling"],
      x=[0,0.25,0.5,0.75,0.99],
      y=[0,0,0,0.75,0.25],
      color = "lightsteelblue"
    ),
    link = dict(
      source = [0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1, # These correspond to the inflows and outflows
                2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,2,3,# These are the flows that go from EOL MGT to reuse and from reuse to recycling
                2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2], # These are the flows that go directly to recycling
      target = [1, 2,  1, 2, 1, 2,1,2, 1, 2,  1, 2, 1, 2,1,2, 1, 2,  1, 2, 1, 2,1,2, 1, 2,  1, 2, 1, 2,1,2,# These correspond to the inflows and outflows
      3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4,3,4, #These are the flows that go from EOL MGT to reuse and from reuse to recycling
      4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4],# These are the flows that go directly to recycling
      color = ["orchid", "orchid","mediumseagreen",  "mediumseagreen", "indianred","indianred", 
            "turquoise", "turquoise", 'orchid', 'orchid',
            'beige', 'beige', 'bisque', 'bisque', 'blue','blue',
            'blueviolet', 'blueviolet', 'cadetblue', 'cadetblue', 
            'darkcyan', 'darkcyan','chocolate', 'chocolate','coral', 'coral',
            'cornflowerblue','cornflowerblue', 'cornsilk','cornsilk','lightblue', 'lightblue',
            "orchid", "orchid","mediumseagreen",  "mediumseagreen", "indianred","indianred", 
            "turquoise", "turquoise", 'orchid', 'orchid',
            'beige', 'beige', 'bisque', 'bisque', 'blue','blue',
            'blueviolet', 'blueviolet', 'cadetblue', 'cadetblue', 
            'darkcyan', 'darkcyan','chocolate', 'chocolate','coral', 'coral',
            'cornflowerblue','cornflowerblue', 'cornsilk','cornsilk', 'lightblue', 'lightblue',
            "orchid","mediumseagreen", "indianred", 
             "turquoise", 'orchid',
             'beige',  'bisque', 'blue',
             'blueviolet',  'cadetblue', 
             'darkcyan', 'chocolate', 'coral',
            'cornflowerblue', 'cornsilk', 'lightblue'],
      label = ["LMO/NMC", "EOL LMO/NMC", "NCA", "EOL NCA", 
      "LFP", "EOL LFP", "NCM111", "EOL NCM111",
      "NCM217", "EOL NCM217", "NCM523", "EOL NCM523",
      "NCM622", "EOL NCM622", "NCM622-Graphite (Si)", "EOL NCM622-Graphite (Si)",
      "NCM712-Graphite (Si)", "EOL NCM712-Graphite (Si)", "NCM811-Graphite (Si)", "EOL NCM811-Graphite (Si)",
      "NCM955-Graphite (Si)", "EOL NCM955-Graphite (Si)", "Li-Air", "EOL Li-Air",
      "Li-Sulphur", "EOL Li-Sulphur", "LNO", "EOL LNO",
      "NCMA", "EOL NCMA", "NiMH", "EOL NiMH",
      "Reused LMO/NMC", "Recycled LMO/NMC", "Reused NCA", "Recycled NCA", 
      "Reused LFP", "Recycled LFP", "Reused NCM111", "Recycled NCM111",
      "Reused NCM217", "Recycled NCM217", "Reused NCM523", "Recycled NCM523",
      "Reused NCM622", "Reused Recycled NCM622", "Reused NCM622-Graphite (Si)", "Recycled NCM622-Graphite (Si)",
      "Reused NCM712-Graphite (Si)", "Recycled NCM712-Graphite (Si)", "Reused NCM811-Graphite (Si)", "Recycled NCM811-Graphite (Si)",
      "Reused NCM955-Graphite (Si)", "Recycled NCM955-Graphite (Si)", "Reused Li-Air", "Recycled Li-Air",
      "Reused Li-Sulphur", "Recycled Li-Sulphur", "Reused LNO", "Recycled LNO",
      "Reused NCMA", "Recycled NCMA", "Reused NiMH", "Recycled NiMH",
      "Recycled LMO/NMC", "Recycled NCA", 
      "Recycled LFP",  "Recycled NCM111",
      "Recycled NCM217",  "Recycled NCM523",
      "Recycled NCM622",  "Recycled NCM622-Graphite (Si)",
      "Recycled NCM712-Graphite (Si)", "Recycled NCM811-Graphite (Si)",
      "Recycled NCM955-Graphite (Si)", "Recycled Li-Air",
      "Recycled Li-Sulphur" "Recycled LNO",
       "Recycled NCMA", "Recycled NiMH"
      ], 
      value = [bat_inflow[stock_scenario,ev_scenario,chem_scenario,0,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,0,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,1,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,1,year-1950],
      bat_inflow[stock_scenario,ev_scenario,chem_scenario,2,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,2,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,3,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,3,year-1950],
      bat_inflow[stock_scenario,ev_scenario,chem_scenario,4,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,4,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,5,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,5,year-1950], 
      bat_inflow[stock_scenario,ev_scenario,chem_scenario,6,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,6,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,7,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,7,year-1950],
      bat_inflow[stock_scenario,ev_scenario,chem_scenario,8,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,8,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,9,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,9,year-1950],
      bat_inflow[stock_scenario,ev_scenario,chem_scenario,10,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,10,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,11,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,11,year-1950], 
      bat_inflow[stock_scenario,ev_scenario,chem_scenario,12,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,12,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,13,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,13,year-1950],
      bat_inflow[stock_scenario,ev_scenario,chem_scenario,14,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,14,year-1950], bat_inflow[stock_scenario,ev_scenario,chem_scenario,15,year-1950], bat_outflow[stock_scenario,ev_scenario,chem_scenario,15,year-1950],
      ### Now we add the reuse and recycling flows
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,year-1950],
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,year-1950],
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,year-1950], 
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,6,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,6,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,7,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,7,year-1950],
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,8,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,8,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,9,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,9,year-1950],
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,10,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,10,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,11,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,11,year-1950], 
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,12,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,12,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,13,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,13,year-1950],
      bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,14,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,14,year-1950], bat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,15,year-1950], bat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,15,year-1950],
      # Now we add the batteries that were recycled directly
      bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,year-1950],
      bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,6,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,7,year-1950],
      bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,8,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,9,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,10,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,11,year-1950], 
      bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,12,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,13,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,14,year-1950], bat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,15,year-1950],
      ] # 
  )), ### Now we can add the material layer
  go.Sankey(domain={
            'x': [0.4, 1],
            'y': [0, 1],
        },
    arrangement="snap",
    node = dict(
      pad = 15,
      thickness = 20,
      line = dict(color = "black", width = 0.5),
      label = ["Material manufacturer", "In use materials", "End of life materials", "Reuse", "Recycling", "Losses"],
      x=[0,0.25,0.4,0.6,0.75,1],
      y=[0,0,0.6,0.6,0.3, 0.3],
      color = "lightsteelblue"
    ),
    link = dict(
      source = [0,1,0,1,0,1,0,1,0,1,0,1, # These correspond to the inflows and outflows
                2,3,2,3,2,3,2,3,2,3,2,3,# These are the flows that go from EOL MGT to reuse and from reuse to recycling
                2,2,2,2,2,2, # These are the flows that go directly to recycling
                4,4,4,4,4,4,# Recycling loop from recycled materials
                4,4,4,4,4,4], # Recycling losses
      target = [1,2,1,2,1,2,1,2,1,2,1,2,# These correspond to the inflows and outflows
                3,4,3,4,3,4,3,4,3,4,3,4, #These are the flows that go from EOL MGT to reuse and from reuse to recycling
                4,4,4,4,4,4, # These are the flows that go directly to recycling
                1,1,1,1,1,1, # Material recycling loop
                5,5,5,5,5,5], # Losses
      color = ["orchid", "orchid","mediumseagreen",  "mediumseagreen", "indianred","indianred", 
            "turquoise", "turquoise", 
            'bisque', 'bisque', 'beige', 'beige',
            "orchid", "orchid","mediumseagreen",  "mediumseagreen", "indianred","indianred", 
            "turquoise", "turquoise", 'bisque', 'bisque', 'beige', 'beige', 
            "orchid", "mediumseagreen",  "indianred", 
            "turquoise",  'bisque',
            'beige',
            "orchid", "mediumseagreen",  "indianred", 
            "turquoise",  'bisque',
            'beige',  
            "orchid", "mediumseagreen",  "indianred", 
            "turquoise",  'bisque',
            'beige'],
      label = ["Li", "EOL Li", "Graphite", "EOL Graphite", 
      "P", "EOL P", "Mn", "EOL Mn",
      "Co", "EOL Co", "Ni", "EOL Ni",
      "Li in reused batteries", "Li to recycling", "Graphite in reused batteries", "Graphite to recycling", 
      "P in reused batteries", "P to recycling", "Mn in reused batteries", "Mn to recycling",
      "Co in reused batteries", "Co to recycling", "Ni in reused batteries", "Ni to recycling",
      "Li to recycling", "Graphite to recycling", 
      "P to recycling",  "Mn to recycling",
      "Co to recycling",  "Ni to recycling",
      "Recycled Li", "Recycled Graphite", 
      "Recycled P",  "Recycled Mn",
      "Recycled Co",  "Recycled Ni",
      "Lost Li", "Lost Graphite", 
      "Lost P",  "Lost Mn",
      "Lost Co",  "Lost Ni",
      ], 
      value = [mat_inflow[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,recycling_process,year-1950], mat_outflow[stock_scenario,ev_scenario,chem_scenario,0,year-1950], mat_inflow[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,recycling_process,year-1950], mat_outflow[stock_scenario,ev_scenario,chem_scenario,1,year-1950],
      mat_inflow[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,recycling_process,year-1950], mat_outflow[stock_scenario,ev_scenario,chem_scenario,2,year-1950], mat_inflow[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,recycling_process,year-1950], mat_outflow[stock_scenario,ev_scenario,chem_scenario,3,year-1950],
      mat_inflow[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,recycling_process,year-1950], mat_outflow[stock_scenario,ev_scenario,chem_scenario,4,year-1950], mat_inflow[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,recycling_process,year-1950], mat_outflow[stock_scenario,ev_scenario,chem_scenario,5,year-1950], 
      ### Now we add the reuse and recycling flows
      mat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,year-1950], mat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,year-1950], mat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,year-1950], mat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,year-1950],
      mat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,year-1950], mat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,year-1950], mat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,year-1950], mat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,year-1950],
      mat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,year-1950], mat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,year-1950], mat_reuse[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,year-1950], mat_reuse_to_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,year-1950], 
      ### Now we add the flows directly to recycling
      mat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,year-1950], mat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,year-1950], mat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,year-1950], mat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,year-1950],
      mat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,year-1950], mat_rec[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,year-1950], 
      ### Now we add the recycling loop
      mat_loop[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,recycling_process,year-1950], mat_loop[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,recycling_process,year-1950], mat_loop[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,recycling_process,year-1950], mat_loop[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,recycling_process,year-1950],
      mat_loop[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,recycling_process,year-1950], mat_loop[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,recycling_process,year-1950],
      ### Now we add the material losses
      ### Now we add the recycling loop
    #   mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,0,year-1950], mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,1,year-1950], mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,2,year-1950], mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,3,year-1950],
    #   mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,4,year-1950], mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,5,year-1950], mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,6,year-1950], mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,7,year-1950],
    #   mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,8,year-1950], mat_loss[stock_scenario,ev_scenario,chem_scenario,reuse_scenario,9,year-1950]  
      ]
  ))])

    fig.update_layout(title_text="Global vehicle fleet model", font_size=16)

    return fig


if __name__ == '__main__':
    app.run_server(host='127.0.0.1', port='8050', debug=True)
