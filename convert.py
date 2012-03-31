import os.path
import json
import urllib

import gobject
import gtk
import pango
import webkit

import pygst
pygst.require('0.10')
import gst

class WebBrowser(gtk.Window):

    def __init__(self):
        gtk.Window.__init__(self)

        self.width = 640
        self.height = 360
        self.framerate = 30000.0 / 1001.0
        self.frameratestr = "30000/1001"
        self.speedup = 2.0

        self.frame_num = 0

        view = webkit.WebView()

        # needed to load other resources
        settings = view.get_settings()
        settings.set_property('enable-file-access-from-file-uris', 1)

        #view.connect("hovering-over-link", self._hovering_over_link_cb)
        view.connect("load-finished", self._view_load_finished_cb)
        view.connect("title-changed", self._title_changed_cb)

        view.set_size_request(self.width, self.height)

        alignment = gtk.Alignment(0.0, 0.0, 0.0, 0.0)
        alignment.add(view)
        self.add(alignment)

        #vbox = gtk.VBox(spacing=1)
        #vbox.pack_start(toolbar, expand=False, fill=False)
        #vbox.pack_start(content_tabs)
        #self.add(vbox)

        self.connect('destroy', destroy_cb)

        self.show_all()

        self.pipeline, self.snapsrc = gst_pipeline(view, "capture.ogg")

        path = os.path.abspath(os.path.dirname(__file__))
        loc = "file://%s/index.html" % path
        args = {
            "embed": 1,
            "track": "synth.gpx",
            "layer": "M",
            "z": 16,
            "step": self.speedup * 1000.0 / self.framerate,
            "width": self.width,
            "height": self.height,
            "pilot": 0,
            "track_colour": "red",
            }
        uri = "%s?%s" % (loc, urllib.urlencode(args))
        print "loading: %s" % uri
        view.load_uri(uri)

    def _view_load_finished_cb(self, view, frame):
        # title = frame.get_title()
        # if not title:
        #     title = frame.get_uri()
        # self.set_title("PyWebKitGtk - %s" % title)
        self.set_title("Converter")

    def _title_changed_cb(self, view, frame, title):
        #self._view_load_finished_cb(view, frame)
        try:
            msg = json.loads(frame.get_title())
        except ValueError:
            msg = None
        if msg:
            f = getattr(self, "_msg_%s" % msg["msg"], None)
            if f:            
                args = msg.get("object", {})
                f(view, **args)
            else:
                print "*** bugger: couldn't call %s" % msg["msg"]

    def execute(self, view, script, timeout=None):
        def idle_execute_script():
            view.execute_script(script)
        if timeout is None:
            gobject.idle_add(idle_execute_script)
        else:
            gobject.timeout_add(timeout, idle_execute_script)

    def _msg_loaded(self, view):
        print "loaded"
        self.execute(view, "console.log('hello, world!');")
        def begin():
            self.execute(view, "Animate.advance();")
        #gobject.timeout_add(2000, begin)
        begin()

    def _msg_frame(self, view):
        #print "Frame %d" % self.frame_num
        self.get_screenshot(view, self.frame_num * 1000 / self.framerate)
        self.frame_num += 1
        self.execute(view, "Animate.advance();", 100)

    def _msg_finished(self, view):
        print "finished"
        self.pipeline.set_state(gst.STATE_NULL)
        destroy_cb(self)

    def get_screenshot(self, widget, time_ms):
        if widget.get_realized():
            snapshot = widget.get_snapshot()
            w, h = snapshot.get_size()
            pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, w, h)
            pixbuf.get_from_drawable(snapshot, widget.get_colormap(),
                                     0, 0, 0, 0, w, h)
            #pixbuf.save(self.frame_filename(frame_num), "png")
            self.snapsrc.add_snapshot(pixbuf, time_ms)

    @staticmethod
    def frame_filename(frame_num):
        if frame_num is None:
            return "frame.png"
        else:
            return "frame%05d.png" % frame_num

def load_requested_cb (widget, text, content_pane):
    if not text:
        return
    content_pane.load(text)

def destroy_cb(window):
    """destroy window resources"""
    window.pipeline.set_state(gst.STATE_NULL)
    window.destroy()
    gtk.main_quit()

class SnapshotSource(gst.Element):

    #here we register our plugin details
    __gstdetails__ = (
        "SnapshotSource plugin",
        "convert.py",
        "gst.Element, that passes a buffer from source to sink (a filter)",
        "Rodney Lorrimar <rodney@rodney.id.au>")

    _src_template = gst.PadTemplate("src",
                                    gst.PAD_SRC,
                                    gst.PAD_ALWAYS,
                                    gst.caps_new_any())

    __gsttemplates__ = (_src_template, )

    def __init__(self, *args, **kwargs):
        gst.Element.__init__ (self, *args, **kwargs)
        self.src_pad = gst.Pad(self._src_template)
        self.src_pad.use_fixed_caps()
        self.add_pad(self.src_pad)
 
    def nonono__init__(self, widget):   
        #initialise parent class
        #gst.Element.__init__(self, *args, **kwargs)
        self.__gobject_init__()

        self.widget = widget

        # #source pad, outgoing data
        # self.srcpad = gst.Pad(self._srctemplate)
        # self.srcpad.set_setcaps_function(self._src_setcaps)
        # self.srcpad.set_chain_function(self._src_chain)
        
        # #sink pad, incoming data
        # #self.sinkpad = gst.Pad(self._sinktemplate)
        
        # #make pads available
        # self.add_pad(self.srcpad)
        # #self.add_pad(self.sinkpad)

    def add_snapshot(self, pixbuf, time_ms):
        self.width = pixbuf.get_width()
        self.height = pixbuf.get_height()
        #print "Pushing %dx%d snapshot to source" % (self.width, self.height)
        buf = gst.Buffer(pixbuf.get_pixels())
        buf.timestamp = int(round(time_ms * gst.MSECOND))
        # Don't forget to set the right caps on the buffer
        self.set_caps_on(buf)
        src = self.get_static_pad("src")
        status = src.push(buf)
        if status != gst.FLOW_OK:
            raise RuntimeError, "Error while pushing buffer : " + str(status)

    def set_caps_on(self, dest):
        """Set the current frame caps on the specified object"""
        # The data is always native-endian xRGB; ffmpegcolorspace
        # doesn't support little-endian xRGB, but does support
        # big-endian BGRx.
        caps = gst.caps_from_string("video/x-raw-rgb,bpp=24,depth=24,\
                                     red_mask=0xff0000,\
                                     green_mask=0x00ff00,\
                                     blue_mask=0x0000ff,\
                                     endianness=4321,\
                                     framerate=30000/1001,\
                                     width=%d,height=%d" \
                                        % (self.width, self.height))
        if dest:
            dest.set_caps(caps)

    def _src_setcaps(self, pad, caps):
        #we negotiate our capabilities here, this function is called
        #as autovideosink accepts anything, we just say yes we can handle the
        #incoming data
        return True
    
    def _src_chain(self, pad, buf):
        #this is where we do filtering
        #and then push a buffer to the next element, returning a value saying
        # it was either successful or not.
        return self.srcpad.push(buf)

#here we register our class with glib, the c-based object system used by
#gstreamer
gobject.type_register(SnapshotSource)

def gst_pipeline(widget, outfile=None):
    ## this code creates the following pipeline, equivalent to 
    ## gst-launch-0.10 SnapshotSource  ! videoscale ! ffmpegcolorspace ! autovideosink

    # first create individual gstreamer elements

    snapsrc = SnapshotSource()
    vscale = gst.element_factory_make("videoscale")
    cspace = gst.element_factory_make("ffmpegcolorspace")

    elements = [snapsrc, vscale, cspace]

    if outfile:
        print "recording to %s" % outfile
        videorate = gst.element_factory_make("videorate")
        theoraenc = gst.element_factory_make("theoraenc")
        oggmux = gst.element_factory_make("oggmux")
        filesink = gst.parse_launch ("filesink location=%s" % outfile)
        if not filesink:
            raise RuntimeError, "Can't create filesink element"
        elements.extend([videorate, theoraenc, oggmux, filesink])
    else:
        vsink = gst.element_factory_make("autovideosink")
        elements.append(vsink)

    # create the pipeline
    p = gst.Pipeline()
    p.add(*elements)
    gst.element_link_many(*elements)

    # set pipeline to playback state
    p.set_state(gst.STATE_PLAYING)

    return p, snapsrc

if __name__ == "__main__":
    webbrowser = WebBrowser()
    gtk.main()
