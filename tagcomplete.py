# -*- coding: utf-8 -*-

# Copyright 2017 Murat Guven <muratg@online.de>
# Updated to gtk3 (zim 0.70)
# This is a plugin for ZimWiki from Jaap Karssenberg <jaap.karssenberg@gmail.com>
#
# This plugin provides auto completion for tags similiar to code completion in code editors.
# When you press the @ key, a list of available tags are shown and can be selected.

# The {AutoCompletion} class can be used to provide auto completion on any given
# list within a given Gtk.TextView widget
# The signal 'tag-selected' is emitted together with the tag as argument when a tag is selected

# V0.93
# Signal added

import logging
from gi.repository import GObject, Gtk, Gdk

from zim.plugins import PluginClass
from zim.gui.mainwindow import MainWindowExtension
from zim.actions import action
from zim.gui.widgets import Window, BrowserTreeView, ScrolledWindow

# @
ACTKEY = 'at'
ACTKEY_keyval = 64

logger = logging.getLogger('zim.plugins.autocompletion')


class AutoCompletionPlugin(PluginClass):

    plugin_info = {
        'name': _('Tag Auto Completion'), # T: plugin name
        'description': _('''\
This plugin provides auto completion for tags. When you press the @ key, 
a list of available tags are shown and can be selected (via tab, space or enter, mouse or cursor).
See configuration for tab key handling.

(V0.91)
'''), # T: plugin description
        'author': "Murat Güven",
        'help': 'Plugins:Tag Auto Completion',
    }

    plugin_preferences = (
        # key, type, label, default
        ('tab_behaviour', 'choice', _('Use tab key to'), 'select', ('select', 'cycle')),
        ('space_selection', 'bool', _('Use also SHIFT + Space key for selection'), False),
    )



class TagAutocompleteWin(MainWindowExtension):

    uimanager_xml = '''
    <ui>
    <menubar name='menubar'>
        <menu action='tools_menu'>
            <placeholder name='plugin_items'>
                <menuitem action='tag_auto_completion'/>
            </placeholder>
        </menu>
    </menubar>
    </ui>
    '''

    def __init__(self, plugin, window):
        self.plugin = plugin
        self.window = window
        self.connectto(window.pageview.textview, 'key-press-event')

    @action(_('Auto_Completion'), ) # T: menu item
    def tag_auto_completion(self):
        text_view = self.window.pageview.textview
        all_tags = self.window.notebook.tags.list_all_tags()
        tag_list = [tag.name for tag in all_tags]
        activation_char = "@"
        tag_auto_completion = AutoCompletion(self.plugin, text_view, self.window, 
                                             activation_char, char_insert=False)
        # tag_list as param for completion method as otherwise the list is added at each activation?
        tag_auto_completion.completion(tag_list)

    def on_key_press_event(self, widget, event):
        if event.keyval == ACTKEY_keyval:
            self.tag_auto_completion()


VIS_COL = 0
DATA_COL = 1
WIN_WIDTH = 260
WIN_HEIGHT = 480

SHIFT = ('Shift_L', 'Shift_R')
KEYSTATES = Gdk.ModifierType.CONTROL_MASK |Gdk.ModifierType.META_MASK| Gdk.ModifierType.MOD1_MASK | Gdk.ModifierType.LOCK_MASK
IGNORE_KEYS = {'Up', 'Down', 'Page_Up', 'Page_Down', 'Left', 'Right', \
               'Home', 'End', 'Menu', 'Scroll_Lock', 'Alt_L', 'Alt_R', \
               'VoidSymbol', 'Meta_L', 'Meta_R', 'Num_Lock', 'Insert', \
               'Delete', 'Pause', 'Control_L', 'Control_R',  \
               'ISO_Level3_Shift', 'Caps_Lock'}

GREY = 65535


class AutoCompletionTreeView(object):


    def __init__(self, model):
        self.model = model

        self.completion_win = Window()
        self.completion_win.set_modal(True)
        self.completion_win.set_keep_above(True)

        self.completion_tree_view = BrowserTreeView(self.model)
        self.completion_tree_view.set_enable_search(False)

        self.completion_scrolled_win = ScrolledWindow(self.completion_tree_view)
        self.completion_win.add(self.completion_scrolled_win)

        self.column = Gtk.TreeViewColumn()
        self.completion_tree_view.append_column(self.column)

        self.renderer_text = Gtk.CellRendererText()
        self.column.pack_start(self.renderer_text, False)
        self.column.set_attributes(self.renderer_text, text=DATA_COL)

        # display an undecorated window with a grey border
        self.completion_scrolled_win.set_size_request(WIN_WIDTH, WIN_HEIGHT)
        self.completion_scrolled_win.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.completion_win.set_decorated(False)
        self.completion_scrolled_win.set_border_width(2)
        # self.completion_scrolled_win.modify_bg(Gtk.StateType.NORMAL, Gdk.Color(GREY))
        self.column.set_min_width(50)

        # hide column
        self.completion_tree_view.set_headers_visible(False)


class AutoCompletion(GObject.GObject):

    # todo: Make cursor visible
    # todo: get theme color to use for frame around completion window
    # todo: handling of modifier in Linux

    # define signal (closure type, return type and arg types)
    __gsignals__ = {
        'tag-selected': (GObject.SignalFlags.RUN_LAST, None, (object,)),
    }

    def __init__(self, plugin, text_view, window, activation_char, char_insert=False):
        '''
        Parameters for using this class:
        - Gtk.TextView
        - the Gtk.Window in which the TextView is added
        - list of unicode elements to be used for completion
        - a character which shall activate the class and if that char shall be inserted
          into the text buffer
        '''
        self.plugin = plugin
        self.text_view = text_view
        self.window = window
        self.activation_char = activation_char
        self.char_insert = char_insert
        self.selected_data = ""
        self.entered_text = ""

        self.real_model = Gtk.ListStore(bool, str)
        self.model = self.real_model.filter_new()
        self.model.set_visible_column(VIS_COL)
        self.model = Gtk.TreeModelSort(self.model)
        self.model.set_sort_column_id(DATA_COL, Gtk.SortType.ASCENDING)
       
        # add F-Keys to ignore them later
        for f_key in range(1, 13):
            IGNORE_KEYS.add('F' + str(f_key))

        GObject.GObject.__init__(self)

    def completion(self, completion_list):
        self.entered_text = ""
       
        self.ac_tree_view = AutoCompletionTreeView(self.model)
        self.tree_selection = self.ac_tree_view.completion_tree_view.get_selection()

        self.fill_completion_list(completion_list)

        buffer = self.text_view.get_buffer()
        cursor = buffer.get_iter_at_mark(buffer.get_insert())

        # insert activation char at cursor pos as it is not shown due to accelerator setting
        if self.activation_char and self.char_insert:
            buffer.insert(cursor, self.activation_char)

        x, y = self.get_iter_pos(self.text_view, self.window)
        self.ac_tree_view.completion_win.move(x, y)
        self.ac_tree_view.completion_win.show_all()

        self.ac_tree_view.completion_win.connect(
            'key_press_event',
            self.do_key_press,
            self.ac_tree_view.completion_win)

        self.ac_tree_view.completion_tree_view.connect(
            'row-activated',
            self.do_row_activated)

    def update_completion_list(self):
        tree_selection = self.ac_tree_view.completion_tree_view.get_selection()
        entered_text = self.entered_text
        # filter list against input (find any)
        
        def filter(model, path, iter):
            data = model[iter][DATA_COL]
            model[iter][VIS_COL] = entered_text.upper() in data.upper()
          
        self.real_model.foreach(filter)
        self.select_match(tree_selection)

    def select_match(self, tree_selection):
        path = None
        entered_text = self.entered_text
        textup = entered_text.upper()
        for index, element in enumerate(self.model):
            # set path = 0 to select first row if there is no hit on below statement
            path = 0
            # select first match of filtered list
            if element[DATA_COL].upper().startswith(textup):
                path = index
                break
        # if there is no match where elements in model
        # starts with entered text, then select first row (=0)
        if path is not None:
            tree_selection.select_path(path)
            self.ac_tree_view.completion_tree_view.scroll_to_cell(path)

    def fill_completion_list(self, completion_list):
        self.real_model.clear()
        for element in completion_list:
            self.real_model.append((True, element))

    def do_row_activated(self, view, path, col):
        self.insert_data()
        self.ac_tree_view.completion_win.destroy()

    def do_key_press(self, widget, event, completion_window):
        keyval_name = Gdk.keyval_name(event.keyval)

        # Ignore special keys
        if keyval_name in IGNORE_KEYS:
            return
        
        if keyval_name == 'Escape':
            completion_window.destroy()
            return

        modifier = event.get_state() & KEYSTATES
        shift_mod = event.get_state() & Gdk.ModifierType.SHIFT_MASK
        buffer = self.text_view.get_buffer()
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        entered_chr = chr(event.keyval)
        
        # delete text from buffer and close if activation_char is identified
        if keyval_name == 'BackSpace':
            cursor.backward_chars(1)
            start = buffer.get_iter_at_mark(buffer.get_insert())
            char = buffer.get_text(start, cursor, include_hidden_chars=False)
            buffer.delete(start, cursor)
            if char == self.activation_char:
                completion_window.destroy()
                return
            self.entered_text = self.entered_text[:-1]
            self.update_completion_list()
        elif event.get_state() & Gdk.ModifierType.SHIFT_MASK and \
                keyval_name == 'space' and self.plugin.preferences['space_selection']:
            self.insert_data(" ")
            completion_window.destroy()
        elif keyval_name == 'Return':
            self.insert_data()
            completion_window.destroy()
        elif keyval_name == "space":
            buffer.insert(cursor, " ")
            completion_window.destroy()
        elif keyval_name == "Tab" or keyval_name == "ISO_Left_Tab":
            if self.plugin.preferences['tab_behaviour'] == 'select':
                self.insert_data()
                completion_window.destroy()
                return
            else:
                # cycle: select next item in tree
                (model, path) = self.tree_selection.get_selected_rows()
                current_path = path[0][0]
                next_path = current_path + 1
                self.tree_selection.select_path(next_path)
        elif keyval_name in SHIFT:
            return
        elif shift_mod:
            buffer.insert(cursor, entered_chr)
            self.entered_text += entered_chr
            self.update_completion_list()
        elif not modifier:
            buffer.insert(cursor, entered_chr)
            self.entered_text += entered_chr
            self.update_completion_list()

    def insert_data(self, space=""):
        tree_selection = self.ac_tree_view.completion_tree_view.get_selection()
        (model, path) = tree_selection.get_selected()

        try:
            # is there any entry left or is the list empty?
            selected_data = model[path][DATA_COL]
        except IndexError:
            # if nothing is selected (say: nothing found and nothing is shown in treeview)
            return

        buffer = self.text_view.get_buffer()
        cursor = buffer.get_iter_at_mark(buffer.get_insert())

        # delete entered text
        n_entered_text = len(self.entered_text)
        cursor.backward_chars(n_entered_text)
        start = buffer.get_iter_at_mark(buffer.get_insert())
        buffer.delete(start, cursor)
        buffer.insert(start, selected_data + space)
        self.emit('tag-selected', selected_data)

    def get_iter_pos(self, textview, window):

        xcorr = WIN_WIDTH
        ycorr = 2
        
        buffer = textview.get_buffer()
        cursor = buffer.get_iter_at_mark(buffer.get_insert())

        top_x, top_y = textview.get_toplevel().get_position()
        iter_location = textview.get_iter_location(cursor)
        mark_x, mark_y = iter_location.x, iter_location.y + iter_location.height
        # calculate buffer-coordinates to coordinates within the window
        win_location = textview.buffer_to_window_coords(Gtk.TextWindowType.WIDGET,
                                                        int(mark_x), int(mark_y))
        line_height = iter_location.height // 2
        
        # now find the right window --> Editor Window and the right pos on screen
        win = textview.get_window(Gtk.TextWindowType.WIDGET)
        view_pos = win.get_position()

        xx = win_location[0] + view_pos[0]
        yy = win_location[1] + view_pos[1] + iter_location.height

        x = top_x + xx + xcorr
        y = top_y + yy + ycorr - line_height
        x, y = self.calculate_with_monitors(x, y, iter_location, window,
                                            xcorr=xcorr, ycorr=ycorr+line_height)
        return (x, y + iter_location.height)
    
    def calculate_with_monitors(self, x, y, iter_location, window, xcorr=0, ycorr=0):
        '''
        Calculate correct x,y position if multiple monitors are used
        '''
        STATUS_BAR_CORRECTION = 30
        screen = window.get_screen()

        cursor_screen = screen.get_monitor_at_point(x, y)
        cursor_monitor_geom = screen.get_monitor_geometry(cursor_screen)

        if x + WIN_WIDTH >= (cursor_monitor_geom.width + cursor_monitor_geom.x):
            diff = x - (cursor_monitor_geom.width + cursor_monitor_geom.x) + WIN_WIDTH
            x = x - diff
            x += xcorr

        if y + iter_location.height + WIN_HEIGHT >= (
                cursor_monitor_geom.height + cursor_monitor_geom.y - STATUS_BAR_CORRECTION):
            diff = WIN_HEIGHT + 2 * iter_location.height
            y = y - diff
            y += ycorr

        return x, y
