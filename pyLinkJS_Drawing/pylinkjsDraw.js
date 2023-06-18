/*jshint esversion: 6 */

// --------------------------------------------------
//  Globals
// --------------------------------------------------
var RENDER_CODE = '';
var DRAG_START_COORD_X = 0;
var DRAG_START_COORD_Y = 0;
var IS_DRAGGING = false;


// --------------------------------------------------
//  Pan and Zoom Functions
// --------------------------------------------------
function force_translate(canvas_working_id, canvas_display_id, x, y){
    // calculate the contexts
    let cand = document.getElementById(canvas_display_id);
    let ctxd = cand.getContext("2d");
    let canw = document.getElementById(canvas_working_id);
    let ctxw = canw.getContext("2d");
    let tm = ctxw.getTransform();

    // reset the translation so the world is back at 0, 0
    ctxw.transform(1, 0, 0, 1, -tm.e / tm.a, -tm.f / tm.d);
    ctxw.transform(1, 0, 0, 1, x, y);
}

function force_zoom(canvas_working_id, canvas_display_id, dx, dy, zoom){
    // calculate the contexts
    let cand = document.getElementById(canvas_display_id);
    let ctxd = cand.getContext("2d");
    let canw = document.getElementById(canvas_working_id);
    let ctxw = canw.getContext("2d");

    // find the coordinates the mouse is in in the working window
    let drect = cand.getBoundingClientRect();
    let tm = ctxw.getTransform();
    let wx = (dx - tm.e) / tm.a;
    let wy = (dy - tm.f) / tm.d;

    // reset translation so the world is back at 0, 0 then set the new zoom
    ctxw.transform(1, 0, 0, 1, -tm.e / tm.a, -tm.f / tm.d);
    ctxw.transform(zoom, 0, 0, zoom, 0, 0);

    // read the new transform matrix
    let tm2 = ctxw.getTransform();
    let offsetx = dx / tm2.a;
    let offsety = dy / tm2.d;
    ctxw.transform(1, 0, 0, 1, -(wx - offsetx), -(wy - offsety));
    rerender();
}

function canvas_init(canvas_working_id, canvas_display_id) {
    // calculate the contexts
    let cand = document.getElementById(canvas_display_id);
    let ctxd = cand.getContext("2d");
    let canw = document.getElementById(canvas_working_id);
    let ctxw = canw.getContext("2d");

    // Handle mouse down to start panning
    $('#' + canvas_display_id).mousedown(function(e) {
        // update the drag coordinates
        IS_DRAGGING = true;
        DRAG_START_COORD_X = e.pageX;
        DRAG_START_COORD_Y = e.pageY;
    });

    // Handle mouse move for panning
    $('#' + canvas_display_id).mousemove(function(e) {
        if (IS_DRAGGING) {
            // scale the panning so it matches mouse movement
            let tm = ctxw.getTransform();
            ctxw.transform(1, 0, 0, 1, (e.pageX - DRAG_START_COORD_X) / tm.a, (e.pageY - DRAG_START_COORD_Y) / tm.d);
            rerender();

            // update the drag coordinates
            DRAG_START_COORD_X = e.pageX;
            DRAG_START_COORD_Y = e.pageY;
        }
    });

    // Handle Mouse up to stop panning
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

    // Handle mouse wheel for zooming
    $('#' + canvas_display_id).bind('mousewheel', function(e) {
        let drect = cand.getBoundingClientRect();
        let dx = e.pageX - drect.left;
        let dy = e.pageY - drect.top;
        let zoom = 1.0 - (e.originalEvent.deltaY / 1000.0);

        force_zoom(canvas_working_id, canvas_display_id, dx, dy, zoom);
    });
}


// --------------------------------------------------
//  Drawing Functions
// --------------------------------------------------
function clear(ctx) {
    var t = ctx.getTransform();
    ctx.fillRect(-t.e / t.a, -t.f / t.d, ctx.canvas.width / t.a, ctx.canvas.height / t.d);
}

function draw_ellipse(ctx, x, y, radiusX, radiusY, rotation, startAngle, endAngle, counterclockwise) {
    ctx.save();
    ctx.transform(1, 0, 0, 1, x, y);
    ctx.beginPath();
    ctx.ellipse(0, 0,  radiusX, radiusY, rotation, startAngle, endAngle, counterclockwise);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
}

function draw_image(ctx, img, x, y, w, h, filter) {
    ctx.filter = filter;
    ctx.drawImage(img, x, y, w, h);
}

function draw_line(ctx, x1, y1, x2, y2) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
}

function draw_roundRect(ctx, x, y, width, height, radii) {
    ctx.save();
    ctx.transform(1, 0, 0, 1, x, y);
    ctx.beginPath();
    ctx.roundRect(0, 0, width, height, radii);
    ctx.fill();
    ctx.stroke();
    ctx.restore();
}

function draw_text(ctx, x, y, text) {
    ctx.save();
    ctx.transform(1, 0, 0, 1, x, y);
    ctx.beginPath();
    ctx.fillText(text, 0, 0);
    ctx.fill();
    ctx.restore();
}

function flip(ctx, ctx_target) {
    ctx_target.drawImage(ctx, 0, 0);
}

function render(code) {
    RENDER_CODE = code;
    rerender();
}

function rerender() {
    eval(RENDER_CODE);
}
