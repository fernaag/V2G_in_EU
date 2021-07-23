

import json
import urllib
import numpy as np
import pandas as pd
from cycler import cycler
import seaborn as sns

import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

inflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_inflow_array.npy') # dims: z,S,r,g,s,t
outflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_outflow_array.npy') # dims: z,S,r,g,s,t
stock = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/vehicle_stock_array.npy')

bat_inflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_inflow_array.npy') # dims: z,S,a,r,b,p,t
bat_outflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_outflow_array.npy') # dims: z,S,a,r,b,p,t
bat_reuse = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_array.npy') # dims: zSaRrbpt
bat_reuse_to_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_reuse_to_recycling_array.npy') # dims: zSaRrbpt
bat_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/battery_recycling_array.npy') # zSaRrbpt
slb_stock = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/slb_stock_array.npy')

mat_inflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_inflow_array.npy') # dims: zSarept
mat_outflow = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_outflow_array.npy') # dims: z,S,a,r,g,b,p,t
mat_reuse = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_array.npy') # dims: zSaRrbpt
mat_reuse_to_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_reuse_to_recycling_array.npy') # dims: zSaRrbpt
mat_rec = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycling_array.npy') # zSaRrbpt
mat_loop = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_recycled_process_array.npy') # zSaRrbpt
mat_loss = np.load('/Users/fernaag/Box/BATMAN/Coding/Global_model/results/arrays/material_losses_array.npy') # zSaRrbpt

chems_list = np.array(['LMO/NMC','NCA','LFP','NCM111','NCM217','NCM523','NCM622','NCM622-Graphite (Si)','NCM712-Graphite (Si)','NCM811-Graphite (Si)','NCM955-Graphite (Si)','Li-Air','Li-Sulphur','LNO','NCMA','NiMH'])
mat_list = np.array(["Li", "Graphite", "Al", "Si", "P", "Mn", "Co",  "Ni", "Cu",  "Other"])

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']
app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

time = np.arange(1950,2051)
ev_time = np.arange(2010,2051)
fig = go.Figure() # or any Plotly Express function e.g. px.bar(...)

app.layout = html.Div([
    html.Div([
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
                options=[{'label': j, 'value': i} for i,j in enumerate(['Stated policies', 'Sustainable development', 'BAU'])],
                value=1
            )]),
        html.Div([
            html.P("Material"),
            dcc.Dropdown(
                id='material',
                options=[{'label': j, 'value': i} for i,j in enumerate(["Li", "Graphite", "Al", "Si", "P", "Mn", "Co",  "Ni", "Cu",  "Other"])],
                value=0
            )]),
        html.Div([
            html.P("Battery chemistry scenario"),
            dcc.Dropdown(
                id='chem_scenario',
                options=[{'label': j, 'value': i} for i,j in enumerate(['NCX', 'LFP', 'Next_gen', 'Roskill'])],
                value=0
            )]),
        html.Div([
            html.P("Reuse scenario"),
            dcc.Dropdown(
                id='reuse_scenario',
                options=[{'label': j, 'value': i} for i,j in enumerate(['LFP 70% reused', 'Direct recycling'])],
                value=0
            )]),
        html.Div([
        dcc.Graph(
            id='inflows',
            hoverData={'points': [{'customdata': '2021'}]}
        )
    ], style={'width': '49%', 'display': 'inline-block', 'padding': '0 20'}),
    html.Div([
        dcc.Graph(id='outflows'),
    ], style={'display': 'inline-block', 'width': '49%'}),
        html.Div([
        dcc.Graph(figure=fig, id="graph")
], style={'width': '49%', 'display': 'inline-block', 'padding': '0 20'}),
        html.Div([
                dcc.Graph(figure=fig, id="slb")
        ], style={'display': 'inline-block', 'width': '49%'})
  ])])


@app.callback(
    Output("graph", "figure"), 
    Input('stock_scenario', 'value'),
    Input('ev_scenario', 'value'))

def bar_plot(stock_scenario, ev_scenario):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    fig = go.Figure(go.Bar(x=time, y=stock[stock_scenario, ev_scenario, 5, 0,:]/1000000, name='ICE'))
    fig.add_trace(go.Bar(x=time, y=stock[stock_scenario, ev_scenario, 5, 1,:]/1000000, name='BEV'))
    fig.add_trace(go.Bar(x=time, y=stock[stock_scenario, ev_scenario, 5, 3,:]/1000000, name='PHEV'))
    fig.update_layout(barmode='stack', title_text="Global vehicle stock", font_size=16)
    fig.update_yaxes(title_text= 'Number of vehicles [billion]')
    fig.update_xaxes(title_text= 'Year')
    return fig

@app.callback(
    Output("inflows", "figure"), 
    Input('stock_scenario', 'value'),
    Input('ev_scenario', 'value'),
    Input('chem_scenario', 'value'))
    

def bar_plot(stock_scenario, ev_scenario, chem_scenario):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    fig = go.Figure(go.Bar()) 
    for i in np.einsum('bpt->b', bat_inflow[stock_scenario, ev_scenario, chem_scenario, 5, :,:,60:]).nonzero()[0].tolist():
        fig.add_trace(go.Bar(x=ev_time, y=bat_inflow[stock_scenario, ev_scenario, chem_scenario, 5, i,0,60:]  , name=chems_list[i]))
    fig.update_layout(barmode='stack', title_text="Battery demand by chemistry", font_size=16)
    fig.update_yaxes(title_text= 'Number of vehicles')
    fig.update_xaxes(title_text= 'Year')
    return fig

@app.callback(
    Output("outflows", "figure"), 
    Input('stock_scenario', 'value'),
    Input('ev_scenario', 'value'),
    Input('chem_scenario', 'value'),
    Input('reuse_scenario', 'value'),
    Input('material', 'value'))

    
def bar_plot(stock_scenario, ev_scenario, chem_scenario, reuse_scenario, material):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    reuse_scenario = reuse_scenario
    material = material
    fig = go.Figure(go.Bar()) 
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=ev_time, y=mat_inflow[stock_scenario, ev_scenario, chem_scenario, reuse_scenario, 5, material,0, 60:]  , name="Primary "+ mat_list[material]))
    fig.add_trace(go.Bar(x=ev_time, y=mat_loop[stock_scenario, ev_scenario, chem_scenario, reuse_scenario, 5, material,0, 60:]  , name="Recycled " + mat_list[material]))
    fig.add_trace(go.Scatter(x=ev_time, y=(mat_loop[stock_scenario, ev_scenario, chem_scenario, reuse_scenario, 5, material,0, 60:]/\
        (mat_inflow[stock_scenario, ev_scenario, chem_scenario, reuse_scenario, 5, material,0, 60:] +\
             mat_loop[stock_scenario, ev_scenario, chem_scenario, reuse_scenario, 5, material,0, 60:]))*100, name="Rec. content"),
    secondary_y=True,)
    fig.update_layout(barmode='stack', title_text="Material demand", font_size=16)
    fig.update_yaxes(title_text="Material demand [Mt]", secondary_y=False)
    fig.update_yaxes(title_text="Recycled content [%]", secondary_y=True)
    fig.update_xaxes(title_text= 'Year')
    return fig

@app.callback(
    Output("slb", "figure"), 
    Input('stock_scenario', 'value'),
    Input('ev_scenario', 'value'),
    Input('chem_scenario', 'value'),
    Input('reuse_scenario', 'value'))

def bar_plot(stock_scenario, ev_scenario, chem_scenario, reuse_scenario):
    stock_scenario = stock_scenario
    ev_scenario = ev_scenario
    chem_scenario = chem_scenario
    reuse_scenario = reuse_scenario
    
    fig = go.Figure(go.Bar()) 
    for i in np.einsum('bpt->b', slb_stock[stock_scenario, ev_scenario, chem_scenario, reuse_scenario, 5, :,:,60:]).nonzero()[0].tolist():
        fig.add_trace(go.Bar(x=ev_time, y=slb_stock[stock_scenario, ev_scenario, chem_scenario, reuse_scenario, 5, i,0,60:] , name=chems_list[i]))
    fig.update_layout(barmode='stack', title_text="Second life battert stock", font_size=16)
    fig.update_yaxes(title_text= 'Weight of modues [tonnes]')
    fig.update_xaxes(title_text= 'Year')
    return fig

if __name__ == '__main__':
    app.run_server(host='127.0.0.1', port='8050', debug=True)
