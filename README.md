# pyLinkJS_Drawing
HTML5 canvas drawing and layered rendering plugin for `pyLinkJS`.

---

### Table of Contents

- **[Installation](#installation)**
- **[Run the Example App](#run-the-example-app)**
- **[Example Files](#example-files)**
- **[How to Use with Codex in VS Code](#how-to-use-with-codex-in-vs-code)**
- **[Documentation](#documentation)**
  - [Event Handlers](#event-handlers)
  - [pluginDrawing](#plugindrawing)
  - [JSDraw](#jsdraw)
  - [Render Objects](#render-objects)
  - [Flight Plans](#flight-plans)
  - [LayerDataSource](#layerdatasource)
  - [LayerRenderer](#layerrenderer)
  - [LayerController](#layercontroller)
  - [LayerApp](#layerapp)
- **[Notes and Gotchas](#notes-and-gotchas)**
- **[LLM Reference (Code Generation Contract)](#llm-reference-code-generation-contract)**

---

## Installation

It is recommended to use a virtual environment.

```bash
# create a project directory and enter it
mkdir -p ~/pyLinkJS_Drawing_demo
cd ~/pyLinkJS_Drawing_demo

# create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# install required packages
python -m pip install git+https://github.com/Snackman8/pyLinkJS
python -m pip install git+https://github.com/Snackman8/pyLinkJS_Drawing
python -m pip install pandas
```

## Run the Example App

```bash
# clone the example source locally
cd ~/pyLinkJS_Drawing_demo
git clone https://github.com/Snackman8/pyLinkJS_Drawing.git
cd ~/pyLinkJS_Drawing_demo/pyLinkJS_Drawing
source ~/pyLinkJS_Drawing_demo/.venv/bin/activate

# run the example app
python examples/pyLinkJS_Drawing_example.py
```

Open:

- `http://localhost:8300`
- If running on another machine, use that machine's IP address and port `8300`.

## Example Files

- `pyLinkJS_Drawing/examples/pyLinkJS_Drawing_example.py`
  - Python app entry point.
  - Defines example datasources and renderers.
- `pyLinkJS_Drawing/examples/pyLinkJS_Drawing_example.html`
  - Demo page with drawing/display canvases and right-side UI panel containers.
- `pyLinkJS_Drawing/examples/data_coords.csv`
  - Indexed world coordinates used to place render objects.
- `pyLinkJS_Drawing/examples/floor_plan.svg`
  - Background image for the demo scene.
- `pyLinkJS_Drawing/examples/Values.csv`
  - Created/updated by the example datasource at runtime.

## How to Use with Codex in VS Code

If you start from an empty folder and want Codex to scaffold a working demo:

1. Open an empty folder in VS Code.
2. Create a file named `pylinkJS_Drawing_codex_instructions.txt`.
3. Copy the full contents of this `README.md` into
   `pylinkJS_Drawing_codex_instructions.txt`.
4. Open Codex in VS Code.
5. Paste the prompt below.

Prompt to use with Codex:

```text
Read pylinkJS_Drawing_codex_instructions.txt in this workspace and follow it as the project spec.

Starting from this empty folder:
1) Create a Python virtual environment named .venv if it does not already exist.
2) Activate/use .venv and install prerequisites needed for pyLinkJS + pyLinkJS_Drawing demos.
3) Create a minimal runnable app (Python + HTML) that uses pyLinkJS_Drawing.
4) The app should display circles with numbers that update over time (random values are fine).
5) Include required pyLinkJS event handlers (ready, reconnect, onmouseup, options_changed).
6) Keep the code simple and well-commented.
7) When the app starts, print the exact browser URL to open in the terminal, e.g. `Open http://localhost:8300 in your browser.`
8) At the end, print exact run commands.

Do not ask me follow-up questions unless something is truly blocking.
```

---

# Documentation

## Event Handlers

The example app wires pyLinkJS callbacks to `LayerApp`:

- `ready(jsc, *args)`
  - Initializes render state for a newly connected client.
- `reconnect(jsc, *args)`
  - Rebuilds client state after reconnect.
- `onmouseup(jsc, x, y, button)`
  - Forwards click/hit-test events to `LayerApp.on_mouseup`.
- `options_changed(jsc, *args)`
  - Refreshes option values from browser controls.

## pluginDrawing

Class: `pyLinkJS_Drawing.drawingPlugin.pluginDrawing`

Purpose:

- Registers `drawing()` on the pyLinkJS client object.
- Injects `pyLinkJS_Drawing/pylinkjsDraw.js` into served pages.

Typical usage:

```python
from pyLinkJS_Drawing.drawingPlugin import pluginDrawing
from pylinkjs.PyLinkJS import run_pylinkjs_app

drawing_plugin = pluginDrawing('ctx_drawing', 'ctx_display')
run_pylinkjs_app(default_html='my_app.html', plugins=[drawing_plugin])
```

## JSDraw

Class: `pyLinkJS_Drawing.drawingPlugin.JSDraw`

Purpose:

- Queues canvas commands in Python and executes them in browser JavaScript.
- Supports double-buffered rendering (`working` canvas -> `display` canvas).

Core methods:

- `clear()`
- `create_image(name, image_src)`
- `gradient_radial(name, x0, y0, r0, x1, y1, r1, color_stops)`
- `render(jsc, clear=True)`

Supported draw calls:

- `ellipse(...)`
- `image(...)`
- `line(...)`
- `roundRect(...)`
- `text(...)`

## Render Objects

Base class: `RenderObject`

Common concrete objects:

- `CircleObject`
- `EllipseObject`
- `RectObject`
- `RoundRectObject`
- `ImageObject`
- `TextObject`

Render objects:

- Hold drawing properties in `props`.
- Can be nested as a tree via `add_child`.
- Support hit-testing via `point_in_obj`.
- Render recursively with inherited transforms/properties.

## Flight Plans

Base class: `FlightPlan`

Built-in implementations:

- `StaticFlightPlan`
  - Fixed position over time.
- `OrbitFlightPlan`
  - Orbit-style motion using center/vector parameters.

Utility:

- `BounceHandler` can modify vector direction based on bounds.

## LayerDataSource

File: `pyLinkJS_Drawing/layerController.py`

Purpose:

- Defines datasource polling contract.
- Stores latest dataframe and fetch timestamps.

Implement in subclasses:

- `@classmethod data_fetch(cls) -> pd.DataFrame`

## LayerRenderer

File: `pyLinkJS_Drawing/layerController.py`

Purpose:

- Defines renderer contract for layer-based updates.
- Merges subscribed datasource data into `_data`.

Implement in subclasses:

- `layer_init(parentObj)`
- `render(parentObj, options)`
- Optional: `get_options()`, `get_tooltip(...)`

## LayerController

File: `pyLinkJS_Drawing/layerController.py`

Purpose:

- Polls datasources on background worker(s).
- Pushes updated data into subscribed renderers.
- Builds HTML/options/status tooltip content.

## LayerApp

File: `pyLinkJS_Drawing/layerController.py`

Purpose:

- High-level runtime wrapper around `LayerController`.
- Initializes scene graph/background image.
- Handles mouse interaction, tooltip updates, options, and periodic rendering.

---

## Notes and Gotchas

1. `pyLinkJS_Drawing` is designed to be used with `pyLinkJS`; install both packages.
2. The plugin JavaScript is injected into HTML templates. Avoid Tornado-template markers (`{{`, `}}`, `{%`, `%}`) in injected JS comments/strings.

---

## LLM Reference (Code Generation Contract)

Use this section when generating code without source access.

### Required Python Imports

```python
from pylinkjs.PyLinkJS import run_pylinkjs_app
from pyLinkJS_Drawing.drawingPlugin import pluginDrawing
from pyLinkJS_Drawing.layerController import LayerDataSource, LayerRenderer, LayerApp
```

### Required Plugin Setup

```python
drawing_plugin = pluginDrawing('ctx_drawing', 'ctx_display')
run_pylinkjs_app(default_html='your_page.html', plugins=[drawing_plugin], extra_settings={...})
```

### Required Event Handlers

- `ready(jsc, *args)` -> call `LAYER_APP.on_ready(jsc, background_image_path, 'ctx_drawing', 'ctx_display')`
- `reconnect(jsc, *args)` -> call `ready(jsc, *args)`
- `onmouseup(jsc, x, y, button)` -> call `LAYER_APP.on_mouseup(jsc, x, y, button)`
- `options_changed(jsc, *args)` -> call `LAYER_APP.on_options_changed(jsc)`

### Required HTML IDs and Structure

The page must include:

- hidden working canvas: `id="Canvas_Drawing"`
- visible display canvas: `id="Canvas_Display"`
- tooltip container: `id="tooltip"`
- options container: `id="options"`
- datasource status container: `id="datasources"`
- property panel container: `id="properties"`

`pylinkjsDraw.js` functions are injected by the plugin (`canvas_init`, `force_zoom`, `force_translate`, `mouse_get_last_position`, etc.).

### LayerDataSource Contract

Subclass `LayerDataSource` and implement the required override:

- Required: `@classmethod data_fetch(cls) -> pandas.DataFrame`

Important fields:

- `name` (unique datasource name)
- `cooldown_period` (seconds between completed fetches)
- `next_fire_time` (`None` disables polling)
- `data` (latest dataframe)

Reference signatures:

```python
class LayerDataSource:
    def __init__(
        self,
        name: str,
        cooldown_period: int = 5,
        next_fire_time: datetime.datetime | None = datetime.datetime(1900, 1, 1),
        initial_data: pandas.DataFrame | None = None,
    ): ...

    @classmethod
    def data_fetch(cls) -> pandas.DataFrame: ...

    def set_data(
        self,
        df: pandas.DataFrame,
        data_fetch_time: datetime.datetime | None = None
    ) -> None: ...
```

### LayerRenderer Contract

Subclass `LayerRenderer` and implement required overrides:

- Required: `layer_init(parentObj) -> None`
- Required: `render(parentObj, options) -> None`

Optional overrides:

- `get_options() -> list[dict]`
- `get_tooltip(...) -> str`
- `on_data_changed(data_dict) -> None`

Reference signatures:

```python
class LayerRenderer:
    def __init__(
        self,
        name: str,
        starting_data_dict: dict[str, pandas.DataFrame] | None = None,
        subscribed_datasources: list[str] | None = None,
    ): ...

    @classmethod
    def _data_dict_to_df(cls, data_dict: dict[str, pandas.DataFrame]) -> pandas.DataFrame: ...

    def get_options(self) -> list[dict]: ...
    def get_tooltip(self, wx, wy, rolist) -> str: ...
    def layer_init(self, parentObj) -> None: ...
    def on_data_changed(self, data_dict: dict[str, pandas.DataFrame]) -> None: ...
    def render(self, parentObj, options: dict) -> None: ...
```

`get_options()` schema:

- Each option dict:
  - `{'id': str, 'text': str, 'type': 'Boolean', 'default_value': bool}`

`get_tooltip(...)` output:

- Return HTML string.
- Return empty string when no tooltip should be shown.

### Data Expectations

- Renderer `_data` is a merged dataframe built from subscribed datasources.
- `data_coords` datasource is expected and used as the index constraint in layer merging.
- Renderers usually subscribe to at least:
  - coordinate datasource (`data_coords`)
  - one or more dynamic datasources

`data_coords` expectation:

- Index: object IDs (for example `D-1`, `D-2`, ...).
- Columns: at minimum `x`, `y` world coordinates.

### LayerApp Construction Pattern

```python
lds_data_coords = LayerDataSource(name='data_coords', next_fire_time=None, initial_data=df_data_coords)
lds_a = MyDataSourceA(...)
lds_b = MyDataSourceB(...)

lr_a = MyRendererA(name='a', starting_data_dict={'data_coords': df_data_coords}, subscribed_datasources=[...])
lr_b = MyRendererB(name='b', starting_data_dict={'data_coords': df_data_coords}, subscribed_datasources=[...])

LAYER_APP = LayerApp(data_sources=[lds_data_coords, lds_a, lds_b], renderers=[lr_a, lr_b])
LAYER_APP.start()
```

`LayerApp` reference methods:

```python
class LayerApp:
    def __init__(self, data_sources, renderers): ...
    @classmethod
    def compute_image_scale(cls, w, h): ...
    @classmethod
    def compute_zoom(cls, canvas_width, canvas_height, image_width, image_height): ...
    def on_mouseup(self, jsc, x, y, button): ...
    def on_options_changed(self, jsc): ...
    def on_ready(self, jsc, background_image_path, drawing_context_name, display_context_name): ...
    def start(self): ...
    def thread_worker(self): ...
```

### LayerController Reference

```python
class LayerController:
    def __init__(self, minimum_datasource_cooldown_period: int = 5): ...
    def start(self) -> None: ...
    def build_options_html(self, jsc) -> str: ...
    def get_datasource_status_messages(self) -> str: ...
    def get_tooltip(self, layer_names, tooltip_idx) -> str: ...
    def render(self, parentObj, options: dict) -> None: ...
    def update_options(self, jsc) -> None: ...
```

### Core Drawing Objects

Common render objects:

- `CircleObject`
- `RectObject`
- `TextObject`
- `ImageObject`
- `RoundRectObject`
- `EllipseObject`

Set/update visual properties through `obj.props[...]` in renderer `render(...)`.

Common fields used in demo objects:

- `visible`
- `fillStyle`
- `strokeStyle`
- `text_str`
- `font`
- `radius`
- `layer_name`
- `idx`

Tree operations:

- `parentObj.add_child(child_obj)`
- `parentObj.children[name]` for lookup/update

### Common Runtime Defaults

- Default demo port: `8300`
- Typical context names: `ctx_drawing`, `ctx_display`
- Typical canvas IDs: `Canvas_Drawing`, `Canvas_Display`

### Lifecycle Call Order (Practical)

1. App starts and plugin is registered.
2. Browser connects and `ready(...)` runs.
3. `ready(...)` initializes image, zoom, render-object tree, and options panel.
4. Datasource polling loop runs in background.
5. On datasource update, controller calls renderer `on_data_changed(...)`.
6. Render loop updates render objects via renderer `render(...)` and pushes frame.
7. UI events call `onmouseup(...)` and `options_changed(...)`.
8. Reconnect path calls `reconnect(...)`, which should rebuild client state.

### Minimal End-to-End Example (No CSV)

`mini_demo.py`

```python
import random
import pandas as pd
from pylinkjs.PyLinkJS import run_pylinkjs_app
from pyLinkJS_Drawing.drawingPlugin import pluginDrawing, CircleObject, TextObject
from pyLinkJS_Drawing.layerController import LayerDataSource, LayerRenderer, LayerApp

# 1x1 transparent PNG data URI (used as background image source)
BLANK_BG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9s2m2jQAAAAASUVORK5CYII="

LAYER_APP = None


def ready(jsc, *args):
    return LAYER_APP.on_ready(jsc, BLANK_BG, "ctx_drawing", "ctx_display")


def reconnect(jsc, *args):
    return ready(jsc, *args)


def onmouseup(jsc, x, y, button):
    return LAYER_APP.on_mouseup(jsc, x, y, button)


def options_changed(jsc, *args):
    return LAYER_APP.on_options_changed(jsc)


class LDS_RandomValues(LayerDataSource):
    def __init__(self, cooldown_period=1):
        super().__init__(name="random_values", cooldown_period=cooldown_period)

    @classmethod
    def data_fetch(cls):
        idx = [f"D-{i}" for i in range(1, 7)]
        vals = [random.randint(0, 100) for _ in idx]
        return pd.DataFrame({"Value": vals}, index=idx)


class LR_Circles(LayerRenderer):
    def layer_init(self, parentObj):
        for idx, row in self._data.iterrows():
            parentObj.add_child(
                CircleObject(
                    name=f"CIRCLE_{idx}",
                    x=row["x"],
                    y=row["y"],
                    radius=8,
                    fillStyle="rgba(0, 128, 255, 0.5)",
                    layer_name=self.name,
                    idx=idx,
                )
            )
            parentObj.add_child(
                TextObject(
                    name=f"TEXT_{idx}",
                    x=row["x"],
                    y=row["y"],
                    text_str="0",
                    fillStyle="black",
                    font="10pt Arial",
                    textAlign="center",
                    textBaseline="middle",
                    layer_name=self.name,
                    idx=idx,
                )
            )

    def get_options(self):
        return [{"id": "show_circles", "text": "Show Circles", "type": "Boolean", "default_value": True}]

    def get_tooltip(self, tooltip_idx):
        if tooltip_idx in self._data.index:
            return f"{tooltip_idx}<br>Value: {int(self._data.loc[tooltip_idx, 'Value'])}<br>"
        return ""

    def render(self, parentObj, options):
        visible = options.get("show_circles", True)
        df = self._data.copy()
        if "Value" in df.columns:
            df["Value"] = df["Value"].fillna(0)
        else:
            df["Value"] = 0

        for idx, row in df.iterrows():
            c = parentObj.children.get(f"CIRCLE_{idx}")
            t = parentObj.children.get(f"TEXT_{idx}")
            if c is not None:
                c.props["visible"] = visible
                c.props["radius"] = max(6, row["Value"] / 8.0)
                c.props["fillStyle"] = "rgba(255, 80, 80, 0.6)" if row["Value"] >= 60 else "rgba(0, 128, 255, 0.5)"
            if t is not None:
                t.props["visible"] = visible
                t.props["text_str"] = str(int(row["Value"]))


def main():
    global LAYER_APP
    port = 8300

    coords = pd.DataFrame(
        {
            "x": [200, 300, 400, 500, 600, 700],
            "y": [220, 260, 210, 300, 250, 280],
        },
        index=[f"D-{i}" for i in range(1, 7)],
    )

    lds_coords = LayerDataSource(name="data_coords", next_fire_time=None, initial_data=coords)
    lds_random = LDS_RandomValues(cooldown_period=1)
    lr = LR_Circles(
        name="circles",
        starting_data_dict={"data_coords": coords},
        subscribed_datasources=[lds_coords.name, lds_random.name],
    )

    LAYER_APP = LayerApp(data_sources=[lds_coords, lds_random], renderers=[lr])
    LAYER_APP.start()

    drawing_plugin = pluginDrawing("ctx_drawing", "ctx_display")
    print(f"Open http://localhost:{port} in your browser.")
    run_pylinkjs_app(default_html="mini_demo.html", plugins=[drawing_plugin], extra_settings={}, port=port)


if __name__ == "__main__":
    main()
```

`mini_demo.html`

```html
<head>
  <script src="https://cdn.jsdelivr.net/npm/jquery@3.6.1/dist/jquery.min.js"></script>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.1/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.2.1/dist/js/bootstrap.bundle.min.js"></script>
</head>
<body>
  <h1>pyLinkJS_Drawing Mini Demo</h1>
  <canvas id="Canvas_Drawing" style="display:none;"></canvas>
  <canvas id="Canvas_Display" style="border:1px solid black;"></canvas>

  <div id="right_pane" style="position:absolute; top:70px; left:850px; width:220px;">
    <h3>Options</h3>
    <div id="options"></div>
    <h3>DataSources</h3>
    <div id="datasources"></div>
    <h3>Properties</h3>
    <div id="properties"></div>
  </div>

  <div id="tooltip" style="visibility:hidden; position:absolute; background:palegoldenrod; border:1px solid black; padding:4px;">Tooltip</div>

  <script>
    let canvas_drawing = null;
    let ctx_drawing = null;
    let canvas_display = null;
    let ctx_display = null;

    function resize() {
      const w = window.innerWidth - 260;
      const h = window.innerHeight - 100;
      canvas_drawing.width = w;
      canvas_display.width = w;
      canvas_drawing.height = h;
      canvas_display.height = h;
      $('#right_pane').css('left', w + 20);
      $('#right_pane').css('height', h);
    }

    $(document).ready(function() {
      canvas_init('Canvas_Drawing', 'Canvas_Display', 'tooltip');
      canvas_drawing = document.getElementById('Canvas_Drawing');
      ctx_drawing = canvas_drawing.getContext('2d');
      canvas_display = document.getElementById('Canvas_Display');
      ctx_display = canvas_display.getContext('2d');
      resize();
      $(window).on('resize', resize);
    });
  </script>
</body>
```

### Code Generation Checklist

Before returning generated code, ensure:

1. Imports include `run_pylinkjs_app`, `pluginDrawing`, and layer base classes.
2. A module-level `LAYER_APP` exists.
3. `ready`, `reconnect`, `onmouseup`, and `options_changed` handlers exist.
4. Plugin is created with `('ctx_drawing', 'ctx_display')`.
5. HTML contains all required IDs.
6. At least one datasource subclass implements `data_fetch`.
7. At least one renderer subclass implements `layer_init` and `render`.
8. `LayerApp` is built with datasources + renderers and `.start()` is called.
9. Startup prints the exact URL to open (for example, `Open http://localhost:8300 in your browser.`).
10. `run_pylinkjs_app(...)` is called with the plugin (and matching `port`).
11. No Tornado template markers (`{{`, `}}`, `{%`, `%}`) are inserted into injected JS comments/strings.
