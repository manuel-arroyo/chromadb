
from threading import Thread

from flask import Flask, render_template
from tornado.ioloop import IOLoop

from bokeh.embed import server_document # type: ignore
from bokeh.layouts import column, row, gridplot # type: ignore
from bokeh.models import Button, ColumnDataSource, Div, Paragraph, Select, TextInput, Toggle, CategoricalColorMapper # type: ignore
from bokeh.plotting import figure # type: ignore
from bokeh.server.server import Server # type: ignore
from bokeh.themes import Theme # type: ignore
from bokeh.events import SelectionGeometry, MouseMove # type: ignore
from bokeh.palettes import d3 # type: ignore
#from gpt4all import GPT4All

# Imports for Chromadb
from db.setup import chroma_setup
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
import chromadb

import numpy as np
import pandas as pd
import requests, time
from functools import partial

app = Flask(__name__)

def getCommonGenesList(df_name_1, df_name_2):
  desc_dataset_path = './db/datasets/genes_human_58347_used_in_sciPlex2_brief_info_by_mygene_package.csv'
  desc_df = pd.read_csv(desc_dataset_path, usecols=["symbol", "summary"]).dropna().drop_duplicates(subset=['symbol'])

  path = f"./db/datasets/impressions_sets/{df_name_1.split('_')[0]}"
  gen_exp_1_df = pd.read_table(path)

  path = f"./db/datasets/impressions_sets/{df_name_2.split('_')[0]}"
  gen_exp_2_df = pd.read_table(path)

  # Merge dataframes on inner gene name.
  # 'symbol' for descriptions, 'sample' for gene expressions
  df = pd.merge(desc_df, gen_exp_1_df, how='inner', left_on='symbol', right_on='sample')
  result_df = pd.merge(df, gen_exp_2_df, how='inner', left_on='symbol', right_on='sample')
  
  gene_list = list(result_df["symbol"])
  return gene_list

def get_sorted_collection_metadata(client, gene_list, collection_name):  
  collection = client.get_collection(collection_name)
  metadatas = collection.get(ids=gene_list, include=["metadatas"])["metadatas"]
  return sorted(metadatas, key=lambda row: row['symbol'])

def get_color_map(df_name):
  path = f"./db/datasets/modified_sets/{df_name}.csv"
  df = pd.read_csv(path)
  
  categories = list(map( lambda x: str(x), df['cluster'].unique()))
  palette = d3['Category10'][len(categories)]
  return CategoricalColorMapper(factors=categories, palette=palette)

def bkapp(doc):
  client = chromadb.PersistentClient(path="./db/local_client")
  
  set_1_name = 'KICH'
  set_2_name = 'KIRP'
  
  common_gene_list = getCommonGenesList(set_1_name, set_2_name)

  summaries_metadatas = get_sorted_collection_metadata(client, common_gene_list, 'gen_summaries')
  expresions_set_1_data = get_sorted_collection_metadata(client, common_gene_list, set_1_name)
  expresions_set_2_data = get_sorted_collection_metadata(client, common_gene_list, set_2_name)
  
  data = {
    'indexes': np.arange(0, len(common_gene_list)),
    'symbol': [d['symbol'] for d in summaries_metadatas],
    'summary': [d['summary'] for d in summaries_metadatas],
    'summary_x': [d['x'] for d in summaries_metadatas],
    'summary_y': [d['y'] for d in summaries_metadatas],
    'set_1_x': [d['x'] for d in expresions_set_1_data],
    'set_1_y': [d['y'] for d in expresions_set_1_data],
    'set_2_x': [d['x'] for d in expresions_set_2_data],
    'set_2_y': [d['y'] for d in expresions_set_2_data]
  }
  source = ColumnDataSource(data) 


  # ----  Datasets Selector ---- #
  select_options = ['ACC', 'BLCA', 'BRCA', 'CESC', 'CHOL', 'COAD', 'COADREAD',
                  'DLBC', 'ESCA', 'GBM', 'HNSC', 'KICH', 'KICH_5', 'KIRC', 'KIRP', 'KIRP_5', 'LAML',
                  'LGG', 'LIHC', 'LUAD', 'LUSC', 'MESO', 'OV1', 'PAAD', 'PCPG',
                  'PRAD', 'READ', 'SARC', 'SKCM', 'STAD', 'TGCT', 'THCA', 'THYM', 'UCEC', 'UCS', 'UVM']
  def change_set_1(attr, old, new):
    set_2_name = select_2.value
    common_gene_list = getCommonGenesList(new, set_2_name)
    expresions_set_1_data = get_sorted_collection_metadata(client, common_gene_list, new)
    
    source.data['set_1_y'] = [d['x'] for d in expresions_set_1_data]
    source.data['set_1_y'] = [d['y'] for d in expresions_set_1_data]
  select_1 = Select(title="Conjunto de datos a visualizar:",
                  value=set_1_name,
                  options=sorted(select_options),
                  sizing_mode="stretch_width", margin=[10, 0])
  select_1.on_change('value', change_set_1)
  select_1.styles = {'padding': '0 25px'}
  
  def change_set_2(attr, old, new):    
    set_1_name = select_1.value
    common_gene_list = getCommonGenesList(new, set_1_name)
    expresions_set_2_data = get_sorted_collection_metadata(client, common_gene_list, new)
    
    source.data['set_2_y'] = [d['x'] for d in expresions_set_2_data]
    source.data['set_2_y'] = [d['y'] for d in expresions_set_2_data]

  select_2 = Select(title="Conjunto de datos a visualizar:",
                  value=set_2_name,
                  options=sorted(select_options),
                  sizing_mode="stretch_width", margin=[10, 0])
  select_2.on_change('value', change_set_2)
  select_2.styles = {'padding': '0 25px'}


  # ---- Summary output Bart-cnn ---- #
  led_h2 = Paragraph(text='Resumen de la selección (led-base-book-summary)')
  led_h2.css_classes = ["h2"]
  led_h2.styles = {
    'padding': '5px 0',
    'display': 'block !important',
    'font-size': '1.17em !important',
    'font-weight': 'bold !important',
    'text-transform': 'uppercase !important'
  }
  led_p = Paragraph(text='The gene selection could not be summarize')
  led_p.styles = {
    'color': '#5C5C5C !important',
    'font-size': '1.2rem !important'
  }
  led_group = column(row(led_h2, margin=[20, 0]), led_p)
  led_group.styles = {'padding': '0 25px'}
  
  bart_h2 = Paragraph(text='Resumen de la selección  (Bart-large-cnn)')
  bart_h2.css_classes = ["h2"]
  bart_h2.styles = {
    'padding': '5px 0',
    'display': 'block !important',
    'font-size': '1.17em !important',
    'font-weight': 'bold !important',
    'text-transform': 'uppercase !important'
  }
  bart_p = Paragraph(text='The gene selection could not be summarize')
  bart_p.styles = {
    'color': '#5C5C5C !important',
    'font-size': '1.2rem !important'
  }
  bart_group = column(row(bart_h2, margin=[20, 0]), bart_p)
  bart_group.styles = {'padding': '0 25px'}
  
  gpt_header = Div(text="", width=200, height=50)
  gpt_p = Paragraph(text='The gene selection could not be summarize')
  gpt_p.styles = {
    'color': '#5C5C5C !important',
    'font-size': '1.2rem !important'
  }
  gpt_group = column(gpt_header, gpt_p)
  gpt_group.styles = {'padding': '0 25px'}
  
  gene_h2 = Div(text="<h2>Genes seleccionados</h2>", width=200, height=50)
  selected_gene_list = []
  gene_display = column()
  gene_display.styles = {'display': 'flex', 'flex-wrap': 'wrap', 'flex-direction': 'row'}
  gene_group = column(gene_h2, gene_display)
  gene_group.styles = {'padding': '0 25px'}
  

  # ---- Plots ---- #
  TOOLTIPS = """
    <div
      class="figure-tootip"
      style="overflow: none; width: 300px" 
    >
      <p><strong>Nombre:</strong>@{symbol}</p>
      <strong>Descripción</strong>
      <p>@{summary}</p>
    </div>
  """
  
  #  -- Plots figures & callbacks
  #     -- Summaries
  summaries_plot = figure(tooltips=TOOLTIPS,
                          match_aspect=True,
                          tools="crosshair,box_select,pan,reset,wheel_zoom,lasso_select",
                          title='Representación semántica de los genes',
                          sizing_mode='scale_width')
  summaries_plot.scatter(x='summary_x', y='summary_y', source=source, marker="circle", radius=0.02, selection_color="red", nonselection_fill_alpha=0.01)

  #     -- Gene expresions
  set_1_plot = figure(name='expresions_plot', match_aspect=True,
      tools="crosshair,box_select,pan,reset,wheel_zoom",
      title='Representación de las expresiones genéticas', tooltips=TOOLTIPS)
  set_1_plot.scatter(x='set_1_x', y='set_1_y', source=source, marker="circle",
                          radius=0.02, selection_color="red",  nonselection_fill_alpha=0.01)
  
  set_2_plot = figure(name='expresions_plot', match_aspect=True,
      tools="crosshair,box_select,pan,reset,wheel_zoom",
      title='Representación de las expresiones genéticas', tooltips=TOOLTIPS)
  set_2_plot.scatter(x='set_2_x', y='set_2_y', source=source, marker="circle",
                       radius=0.02, selection_color="red",  nonselection_fill_alpha=0.01)
  
  def callback_handler(event):    
    gene_name = event.item.text
    print(f"Se hizo clic en el enlace para el gen {gene_name}")
  
  def select_group(event):
    if event.final is True:
      indices = source.selected.indices
      
      gen_descriptions = '.'.join(map(str, np.take(source.data['summary'], indices).tolist()))
            
      gpt_response = requests.post('http://127.0.0.1:5000/summarize',
               data={
                 'gen_descriptions': gen_descriptions
               })
      gpt_header.text = '<h2>Descripciones resumidas (GTP2)</h2>'
      selection_summary = 'The gene selection could not be summarize'
      if (gpt_response.status_code == 200):
        selection_summary = gpt_response.text
      gpt_p.text = selection_summary
          
            ## bart-large-cnn summarization
      #if(True):
      #  bart_response = requests.post('http://127.0.0.1:5000/summarize_bart',
      #                   data={
      #                     'summary_text': list(source.data['summary'][indices])
      #                   })
      #  bart_h2.text = 'Resumen de la selección (Bart-large-cnn)'
      #  selection_summary = 'The gene selection could not be summarize'
      #  if (bart_response.status_code == 200):
      #    selection_summary = bart_response.text
      #  bart_p.text = selection_summary
      #
      ## led-base-book-summary summarization
      #if(True):
      #  led_response = requests.post('http://127.0.0.1:5000/summarize_led',
      #           data={
      #             'summary_text': gen_descriptions
      #           })
      #  led_h2.text = 'Resumen de la selección (led-base-book-summary)'
      #  selection_summary = 'The gene selection could not be summarize'
      #  if (led_response.status_code == 200):
      #    selection_summary = led_response.text
      #  led_p.text = selection_summary
      #        
      selected_gene_list = []
      for gene in np.take(source.data['symbol'], indices).tolist():      
        link_html = f"<a href='#'>{gene}</a>"
        div_enlace = Div(text=link_html)
        div_enlace.on_event('click', callback_handler)
        
        selected_gene_list.append(div_enlace)
      gene_display.children = selected_gene_list

  summaries_plot.on_event(SelectionGeometry, select_group)
  set_1_plot.on_event(SelectionGeometry, select_group)
  set_2_plot.on_event(SelectionGeometry, select_group)

  #  -- Visualization
  plots = gridplot([[summaries_plot, column([select_1, set_1_plot], sizing_mode='scale_both'), column([select_2, set_2_plot], sizing_mode='scale_width')]], sizing_mode='scale_both')
  plots.styles = {'padding': '0 25px'}

  doc.add_root(column([row(plots, sizing_mode='scale_both', min_height=700), gpt_group, gene_group], sizing_mode="scale_width"))
  doc.theme = Theme(filename="theme.yaml")

def searcher(doc):
  # region Plots
  client = chromadb.PersistentClient(path="./db/local_client")
  
  set_1_name = 'KICH_clustering-spectral'
  set_2_name = 'KIRP_clustering-spectral'
  
  common_gene_list = getCommonGenesList(set_1_name, set_2_name)

  summaries_metadatas = get_sorted_collection_metadata(client, common_gene_list, 'gen_summaries')
  expresions_set_1_data = get_sorted_collection_metadata(client, common_gene_list, set_1_name)
  expresions_set_2_data = get_sorted_collection_metadata(client, common_gene_list, set_2_name)
  
  data = {
    'indexes': np.arange(0, len(common_gene_list)),
    'symbol': [d['symbol'] for d in summaries_metadatas],
    'summary': [d['summary'] for d in summaries_metadatas],
    'summary_x': [d['x'] for d in summaries_metadatas],
    'summary_y': [d['y'] for d in summaries_metadatas],
    'set_1_x': [d['x'] for d in expresions_set_1_data],
    'set_1_y': [d['y'] for d in expresions_set_1_data],
    'set_1_cluster': [str(d['cluter']) for d in expresions_set_1_data],
    'set_2_x': [d['x'] for d in expresions_set_2_data],
    'set_2_y': [d['y'] for d in expresions_set_2_data],
    'set_2_cluster': [str(d['cluter']) for d in expresions_set_2_data]
  }
  source = ColumnDataSource(data) 

  TOOLTIPS = """
    <div
      class="figure-tootip"
      style="overflow: none; width: 300px" 
    >
      <p><strong>Nombre:</strong>@{symbol}</p>
      <strong>Descripción</strong>
      <p>@{summary}</p>
    </div>
  """
  color_map = get_color_map(set_1_name)

  
  #  -- Plots figures & callbacks
  summaries_plot = figure(tooltips=TOOLTIPS,
                          match_aspect=True,
                          tools="crosshair,box_select,pan,reset,wheel_zoom,lasso_select",
                          title='Representación semántica de los genes',
                          sizing_mode='scale_width')
  summaries_plot.scatter(x='summary_x', y='summary_y', source=source, marker="circle", radius=0.02, selection_color="red", nonselection_fill_alpha=0.01)
  
  set_1_plot = figure(name='expresions_plot', match_aspect=True,
      tools="crosshair,box_select,pan,reset,wheel_zoom",
      title='Representación de las expresiones genéticas', tooltips=TOOLTIPS)
  set_1_plot.scatter(x='set_1_x', y='set_1_y', source=source, marker="circle",
                          radius=0.02, selection_color="red",  nonselection_fill_alpha=0.01,
                          color={'field': 'set_1_cluster', 'transform': color_map})
  
  set_2_plot = figure(name='expresions_plot', match_aspect=True,
      tools="crosshair,box_select,pan,reset,wheel_zoom",
      title='Representación de las expresiones genéticas', tooltips=TOOLTIPS)
  set_2_plot.scatter(x='set_2_x', y='set_2_y', source=source, marker="circle",
                       radius=0.02, selection_color="red",  nonselection_fill_alpha=0.01,
                       color={'field': 'set_2_cluster', 'transform': color_map})
  #endregion
  
  #region Plot Actions
  def filter_points_near_point(x_ref, y_ref, x_list, y_list, max_distance):
    index_list = []
    for i, (x, y) in enumerate(zip(x_list, y_list)):
      distance = ((x - x_ref)**2 + (y - y_ref)**2)**0.5
      if distance < max_distance:
          index_list.append(i)
          
    return index_list
          
  def brushing(e, plot_name):
    if not brusshing_toggle.active: return

    x = e.x
    y = e.y
    
    x_list = source.data[f"{plot_name}_x"]
    y_list = source.data[f"{plot_name}_y"]
    
    start_time = time.time()
    index = filter_points_near_point(x, y, x_list, y_list, 0.33)
    end_time = time.time()
    source.selected.indices = index
    print("Chunk resumido\n")
    print("           '    ")
    print("         o      ")
    print(f"Tiempo indices: {end_time - start_time} s")
    print("       0        ")
    print("        o       ")  
    print(f"x: {x}, y: {y}")
        
  summaries_plot.on_event(MouseMove, partial(brushing, plot_name='summary'))
  set_1_plot.on_event(MouseMove, partial(brushing, plot_name='set_1'))
  set_2_plot.on_event(MouseMove, partial(brushing, plot_name='set_2'))
  #endregion
  
  #region Plot Widgets
  select_options = ['ACC', 'BLCA', 'BRCA', 'CESC', 'CHOL', 'COAD', 'COADREAD',
                  'DLBC', 'ESCA', 'GBM', 'HNSC', 'KICH', 'KICH_5', 'KIRC', 'KIRP', 'KIRP_5', 'LAML',
                  'LGG', 'LIHC', 'LUAD', 'LUSC', 'MESO', 'OV1', 'PAAD', 'PCPG',
                  'PRAD', 'READ', 'SARC', 'SKCM', 'STAD', 'TGCT', 'THCA', 'THYM', 'UCEC', 'UCS', 'UVM']
  def change_set_1(attr, old, new):
    set_2_name = select_2.value
    common_gene_list = getCommonGenesList(new, set_2_name)
    expresions_set_1_data = get_sorted_collection_metadata(client, common_gene_list, new)
    
    source.data['set_1_y'] = [d['x'] for d in expresions_set_1_data]
    source.data['set_1_y'] = [d['y'] for d in expresions_set_1_data]
  select_1 = Select(title="Conjunto de datos a visualizar:",
                  value=set_1_name,
                  options=sorted(select_options),
                  sizing_mode="stretch_width", margin=[10, 0])
  select_1.on_change('value', change_set_1)
  select_1.styles = {'padding': '0 20px'}

  def change_set_2(attr, old, new):    
    set_1_name = select_1.value
    common_gene_list = getCommonGenesList(new, set_1_name)
    expresions_set_2_data = get_sorted_collection_metadata(client, common_gene_list, new)
    
    source.data['set_2_y'] = [d['x'] for d in expresions_set_2_data]
    source.data['set_2_y'] = [d['y'] for d in expresions_set_2_data]
  select_2 = Select(title="Conjunto de datos a visualizar:",
                  value=set_2_name,
                  options=sorted(select_options),
                  sizing_mode="stretch_width", margin=[10, 0])
  select_2.on_change('value', change_set_2)
  select_2.styles = {'padding': '0 20px'}

  def summarize_selection():
    indices = source.selected.indices    
    gene_descriptions = ('. ').join(map(str, np.take(source.data['summary'], indices).tolist()))

    #model = GPT4All("orca-mini-3b-gguf2-q4_0.gguf")
    #with model.chat_session():
    #  response = model.generate(prompt=f"Can you say what functions share these gene summaries: {gene_descriptions}", temp=0)
    #  summary_div.text = '\
    #    <h2>Descripciones resumidas</h2> \
    #    <p>${response.content}</p>'
  sum_btn = Button(label="Resumir selección", sizing_mode="stretch_width", margin=[10, 0])
  sum_btn.on_click(summarize_selection)
  sum_btn.styles = {'margin-top': '20px'}
  
  brusshing_toggle = Toggle(label="Brushing", sizing_mode="stretch_width", margin=[10, 50])
  brusshing_toggle.styles = {'margin-top': '20px'}
  #endregion
  
  #region SearchBar
  def search_query(attr, old, new):
    client = chromadb.PersistentClient(path="./db/local_client")
    collection = client.get_collection("gen_summaries")
    results = collection.query(
      query_texts=new,
      n_results=200)
    
    results['metadatas'][0][0]
    
    h1.text = '<h2>Genes seleccionados</h2>'
    results_widgets = []
    result_list.children = []
    for result in results['metadatas'][0]:
      result_group = column(sizing_mode="stretch_width")
      
      # Add results to Div (gene list view)
      header = Div(text=f"<h2>{result['symbol']}</h2>")
      header.styles = {'padding': '0 25px'}
      result_group.children.append(header)   
      text = Div(text=f"<p>{result['summary']}</p>")
      text.styles = {'padding': '0 25px'}
      result_group.children.append(text)  
      
      results_widgets.append(result_group)
    result_list.children = list(results_widgets)
    
    symbols = list(map(lambda r: r['symbol'], results['metadatas'][0]))
    indices = []
    for sym in symbols:
      try:
          indice = source.data['symbol'].index(sym)
          indices.append(indice)
      except ValueError:
          pass  # Ignorar símbolos que no están en source.data['symbol']
    source.selected.indices = indices
  search_bar = TextInput(title="Conjunto de datos a visualizar:",
                        placeholder='Introduce la descripción del gen...',
                        sizing_mode="stretch_width", margin=[10, 0])
  search_bar.on_change('value', search_query)
  search_bar.styles = {'padding': '0 25px'}
  #endregion
  
  #region Display
  summary_div = Div(text="")
  h1 = Div(text="<h1></h1>")
  h1.styles = {'padding': '0 25px'}
  result_list = column(sizing_mode="stretch_width")

  plots = gridplot([[row(sum_btn, brusshing_toggle), select_1, select_2], [summaries_plot, set_1_plot, set_2_plot]], sizing_mode='scale_width')
  plots.styles = {'padding': '0 25px'}
  
  doc.add_root(column([search_bar, row(plots, sizing_mode='scale_both', min_height=700), h1, result_list], sizing_mode="scale_width"))
  doc.theme = Theme(filename="theme.yaml")
  #endregion
  
@app.route('/searcher', methods=['GET'])
def searcher_page():
  script = server_document('http://localhost:5006/searcher')
  return render_template("searcher.html", script=script, template="Flask")

@app.route('/', methods=['GET'])
def bkapp_page():
  script = server_document('http://localhost:5006/bkapp')
  return render_template("index.html", script=script, template="Flask")

def bk_worker():
    # Can't pass num_procs > 1 in this configuration. If you need to run multiple
    # processes, see e.g. flask_gunicorn_embed.py
    server = Server({'/bkapp': bkapp, '/searcher': searcher}, io_loop=IOLoop(), allow_websocket_origin=["localhost:8000"])
    server.start()
    server.io_loop.start()

Thread(target=bk_worker).start()


if __name__ == '__main__':    
  chroma_setup()
  print('Opening single process Flask app with embedded Bokeh application on http://localhost:8000/')
  print()
  print('Multiple connections may block the Bokeh app in this configuration!')
  print('See "flask_gunicorn_embed.py" for one way to run multi-process')
  app.run(port=8000)
