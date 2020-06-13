import os
import sys
import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objects as go

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

from dash_app.knowledge_base.last_activity import last_recorded_activity
from dash_app.knowledge_base.backmarket_work_analysis import get_bm_start_times_graph_data
last_activity = last_recorded_activity()
bm_start_time_graph = get_bm_start_times_graph_data()

colors = {
    'background': '#111111',
    'text': '#7FDBFF'
}

app.layout = html.Div(style={'backgroundColor': colors['background']}, children=[
    html.H1(
        children='Hello Dash',
        style={
            'textAlign': 'center',
            'color': colors['text']
        }
    ),

    html.Div(children='Dash: A web application framework for Python.', style={
        'textAlign': 'center',
        'color': colors['text']
    }),
    html.Div(f"""Currently working on {last_activity["project"]}""", style={'textAlign': 'center', 'color': colors['text']}),
    html.Div(f"""It started on {last_activity["start_time"]}""", style={'textAlign': 'center', 'color': colors['text']}),
    html.Div(f"""end_date is {last_activity["end_time"]}""", style={'textAlign': 'center', 'color': colors['text']}),

    dcc.Graph(
        id='backmarket-analysis-1',
        figure={
            'data': [
                {'x': bm_start_time_graph[0], 'y': bm_start_time_graph[1]}
            ]
        }
    )
])


if __name__ == '__main__':
    app.run_server(debug=True)
