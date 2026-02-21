/*jshint esversion: 6 */
// Injected into pyLinkJS pages by pyLinkJS_Drawing.pluginDrawing.inject_html_top().

// --------------------------------------------------
//  Globals
// --------------------------------------------------
var RENDER_CODE = '';
var DRAG_START_COORD_X = 0;
var DRAG_START_COORD_Y = 0;
var IS_DRAGGING = false;
var LAST_MOUSE_WX = 0;
var LAST_MOUSE_WY = 0;
var LAST_MOUSE_PX = 0;
var LAST_MOUSE_PY = 0;
var LAST_MOUSE_TIME = 0;


// --------------------------------------------------
//  Pan/Zoom Helpers
// --------------------------------------------------
/**
 * Force world translation to a specific offset.
 *
 * @param {string} canvas_working_id
 * @param {string} canvas_display_id
 * @param {number} x
 * @param {number} y
 */
function force_translate(canvas_working_id, canvas_display_id, x, y){
    // Resolve canvas contexts.
    let cand = document.getElementById(canvas_display_id);
    let ctxd = cand.getContext("2d");
    let canw = document.getElementById(canvas_working_id);
    let ctxw = canw.getContext("2d");
    let tm = ctxw.getTransform();

    // Reset translation so world origin is at (0, 0), then apply offset.
    ctxw.transform(1, 0, 0, 1, -tm.e / tm.a, -tm.f / tm.d);
    ctxw.transform(1, 0, 0, 1, x, y);
}

/**
 * Force zoom around a display-space anchor point.
 *
 * @param {string} canvas_working_id
 * @param {string} canvas_display_id
 * @param {number} dx Display-space x coordinate.
 * @param {number} dy Display-space y coordinate.
 * @param {number} zoom Zoom multiplier.
 */
function force_zoom(canvas_working_id, canvas_display_id, dx, dy, zoom){
    // Resolve canvas contexts.
    let cand = document.getElementById(canvas_display_id);
    let ctxd = cand.getContext("2d");
    let canw = document.getElementById(canvas_working_id);
    let ctxw = canw.getContext("2d");

    // Convert display-space anchor to world-space coordinates.
    let drect = cand.getBoundingClientRect();
    let tm = ctxw.getTransform();
    let wx = (dx - tm.e) / tm.a;
    let wy = (dy - tm.f) / tm.d;

    // Reset translation, apply new zoom, then restore anchor alignment.
    ctxw.transform(1, 0, 0, 1, -tm.e / tm.a, -tm.f / tm.d);
    ctxw.transform(zoom, 0, 0, zoom, 0, 0);

    // Read new transform and compute anchor-preserving offset.
    let tm2 = ctxw.getTransform();
    let offsetx = dx / tm2.a;
    let offsety = dy / tm2.d;
    ctxw.transform(1, 0, 0, 1, -(wx - offsetx), -(wy - offsety));
    rerender();
}

/**
 * Attach pan/zoom/mouse event handlers to the display canvas.
 *
 * @param {string} canvas_working_id
 * @param {string} canvas_display_id
 * @param {string} tooltip_id
 */
function canvas_init(canvas_working_id, canvas_display_id, tooltip_id) {
    // Resolve canvas contexts.
    let cand = document.getElementById(canvas_display_id);
    let ctxd = cand.getContext("2d");
    let canw = document.getElementById(canvas_working_id);
    let ctxw = canw.getContext("2d");

    // Start panning on mouse down.
    $('#' + canvas_display_id).mousedown(function(e) {
        // Cache drag start coordinates.
        IS_DRAGGING = true;
        DRAG_START_COORD_X = e.pageX;
        DRAG_START_COORD_Y = e.pageY;
    });

    // Pan while dragging.
    $('#' + canvas_display_id).mousemove(function(e) {
        if (IS_DRAGGING) {
            // Scale panning by current zoom so visual drag speed is consistent.
            let tm = ctxw.getTransform();
            ctxw.transform(1, 0, 0, 1, (e.pageX - DRAG_START_COORD_X) / tm.a, (e.pageY - DRAG_START_COORD_Y) / tm.d);
            rerender();

            // Update drag origin.
            DRAG_START_COORD_X = e.pageX;
            DRAG_START_COORD_Y = e.pageY;
        }
    });

    // Stop panning and emit optional mouse-up callback.
    $('#' + canvas_display_id).mouseup(function(e) {
        IS_DRAGGING = false;

        let drect = cand.getBoundingClientRect();
        let dx = e.pageX - drect.left;
        let dy = e.pageY - drect.top;
        let tm = ctxw.getTransform();
        let wx = (dx - tm.e) / tm.a;
        let wy = (dy - tm.f) / tm.d;
        call_py_optional('onmouseup', wx, wy, e.button);
    });

    // Also forward mouse-up events from the tooltip element.
    $('#' + tooltip_id).mouseup(function(e) {
        IS_DRAGGING = false;

        let drect = cand.getBoundingClientRect();
        let dx = e.pageX - drect.left;
        let dy = e.pageY - drect.top;
        let tm = ctxw.getTransform();
        let wx = (dx - tm.e) / tm.a;
        let wy = (dy - tm.f) / tm.d;
        call_py_optional('onmouseup', wx, wy, e.button);
    });

    // Cache latest pointer position for server-side tooltip checks.
    $('#' + canvas_display_id).mousemove(function(e) {
        let drect = cand.getBoundingClientRect();
        let dx = e.pageX - drect.left;
        let dy = e.pageY - drect.top;
        let tm = ctxw.getTransform();
        let wx = (dx - tm.e) / tm.a;
        let wy = (dy - tm.f) / tm.d;
        LAST_MOUSE_WX = wx;
        LAST_MOUSE_WY = wy;
        LAST_MOUSE_PX = e.pageX;
        LAST_MOUSE_PY = e.pageY;
        var d = new Date();
        LAST_MOUSE_TIME = d.getTime();
    });

    // Zoom around cursor on wheel input.
    $('#' + canvas_display_id).bind('mousewheel', function(e) {
        let drect = cand.getBoundingClientRect();
        let dx = e.pageX - drect.left;
        let dy = e.pageY - drect.top;
        let zoom = 1.0 - (e.originalEvent.deltaY / 1000.0);

        force_zoom(canvas_working_id, canvas_display_id, dx, dy, zoom);
    });
}


// --------------------------------------------------
//  Drawing Primitives
// --------------------------------------------------
/**
 * Clear the visible world-space area based on current transform.
 *
 * @param {CanvasRenderingContext2D} ctx
 */
function clear(ctx) {
    var t = ctx.getTransform();
    ctx.fillRect(-t.e / t.a, -t.f / t.d, ctx.canvas.width / t.a, ctx.canvas.height / t.d);
}

/**
 * Draw an ellipse centered at (x, y).
 */
function draw_ellipse(ctx, x, y, radiusX, radiusY, rotation, startAngle, endAngle, counterclockwise) {
    ctx.save();
    ctx.transform(1, 0, 0, 1, x, y);
    ctx.beginPath();
    ctx.ellipse(0, 0,  radiusX, radiusY, rotation, startAngle, endAngle, counterclockwise);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
}

/**
 * Draw an image with an optional CSS filter string.
 */
function draw_image(ctx, img, x, y, w, h, filter) {
    ctx.filter = filter;
    ctx.drawImage(img, x, y, w, h);
}

/**
 * Draw a line segment from (x1, y1) to (x2, y2).
 */
function draw_line(ctx, x1, y1, x2, y2) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
}

/**
 * Draw a rounded rectangle with corner radii.
 */
function draw_roundRect(ctx, x, y, width, height, radii) {
    ctx.save();
    ctx.transform(1, 0, 0, 1, x, y);
    ctx.beginPath();
    ctx.roundRect(0, 0, width, height, radii);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
}

/**
 * Draw text anchored at (x, y).
 */
function draw_text(ctx, x, y, text) {
    ctx.save();
    ctx.transform(1, 0, 0, 1, x, y);
    ctx.beginPath();
    ctx.fillText(text, 0, 0);
    ctx.fill();
    ctx.restore();
}

/**
 * Copy working canvas content to display canvas.
 */
function flip(ctx, ctx_target) {
    ctx_target.drawImage(ctx, 0, 0);
}

/**
 * Cache render code and trigger immediate draw.
 *
 * @param {string} code JavaScript render body to evaluate.
 */
function render(code) {
    RENDER_CODE = code;
    rerender();
}

/**
 * Re-render using cached JavaScript draw code.
 */
function rerender() {
    eval(RENDER_CODE);
}


// --------------------------------------------------
//  Mouse State Query
// --------------------------------------------------
/**
 * Return last known pointer position in world/display coordinates.
 *
 * @returns {Object} Object with keys: wx, wy, px, py, elapsed_ms.
 */
function mouse_get_last_position() {
    var d = new Date();
    var elapsed_ms = d.getTime() - LAST_MOUSE_TIME;
    
    return {'wx': LAST_MOUSE_WX, 'wy': LAST_MOUSE_WY, 'px': LAST_MOUSE_PX, 'py': LAST_MOUSE_PY, 'elapsed_ms': elapsed_ms};    
}
