import sublime
import sublime_plugin
import sublime_api
import datetime, getpass
import re

import subprocess
import threading
import os

# 插数字
class InsertNumberCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.window().show_input_panel("input start and step:", "start:1, step:1", lambda text: self.view.run_command('insert_number_cb', {"text": text}), None, None)


class InsertNumberCbCommand(sublime_plugin.TextCommand):
    def run(self, edit, text):
        # sublime.message_dialog(text)
        text =  re.sub(r"[^\d\+-]*([\+-]?\d+)[,\s\t]+[^\d\+-]*([\+-]?\d+)", r"\1 \2", text)
        numbers = text.split(" ")
        start_num   = int(numbers[0])
        diff_num    = int(numbers[1])
        for region in self.view.sel():
            #(row,col) = self.view.rowcol(region.begin())
            self.view.insert(edit, region.end(), "%d" %start_num)
            start_num += diff_num

# 求和
class SumCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        sum_all = 0
        for region in self.view.sel():
            add = 0
            str_region = self.view.substr(region)
            try:
                add = int(str_region)
            except ValueError:
                sublime.error_message(u"含有非数字的字符串")
                return
            sum_all = sum_all + add

        sublime.message_dialog(str(sum_all))

class SelectWordCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        for region in self.view.sel():
            reg = self.view.word(region)
            self.view.sel().add(reg)
# 多行对齐
class AutoAlignmentCommand(sublime_plugin.TextCommand):
    def auto_align(self, edit):
        pre_row = -1
        pos_max_x = 0.0
        for region in self.view.sel():
            (row,col) = self.view.rowcol(region.begin())
            if row == pre_row:
                sublime.error_message(u"不能在同一行选中两个位置！！")
                return -1
            pre_row = row
            point_begin = region.begin()
            vec_pos = self.view.text_to_layout(point_begin)
            if vec_pos[0] > pos_max_x:
                print(vec_pos[0])
                pos_max_x = vec_pos[0]

        is_finished = True
        for region in self.view.sel():
            pos_cur_x = self.view.text_to_layout(region.begin())[0]
            print("pos_cur_x", pos_cur_x)
            if pos_cur_x < pos_max_x:
                self.view.insert(edit, region.begin(), "\t")
                is_finished = False

        return is_finished

    def run(self, edit):
        count = 0
        while True:
            # 防止死循环,最多循环50次
            count = count + 1
            ret = self.auto_align(edit)
            if count > 50 or ret == -1 or ret == True:
                return

# 独立选择每一行(在当前选中范围内)
class SelectEverySingleLine(sublime_plugin.TextCommand):
    def run(self, edit):
        # self.view.run_command('select_all')
        # for region in self.view.lines(sublime.Region(0, self.view.size())):
        #     self.view.selection.add(region)

        lines = []
        for region in self.view.sel():
            for l in self.view.lines(region):
                if l.a != l.b:
                    lines.append(l)
                # self.view.selection.add(l)
        self.view.selection.clear()
        for l in lines:
            self.view.selection.add(l)

class ShowOutputPanel(sublime_plugin.TextCommand):
    def run(self, edit):
        w = self.view.window()
        w.run_command('show_panel', {'panel': 'output.exec'})

class MyFuckPyBuildCommand(sublime_plugin.WindowCommand):
    encoding = 'utf-8'
    killed = False
    proc = None
    panel = None
    panel_lock = threading.Lock()

    def is_enabled(self, kill=False):
        # The Cancel build option should only be available
        # when the process is still running
        if kill:
            return self.proc is not None and self.proc.poll() is None
        return True

    def detect_version(self):
        fname = self.window.active_view ().file_name()
        with open(fname, 'r', encoding='utf-8') as f:
            line = f.readline()

        m = re.search(r'(python[0-9\.]*)', line)
        if m and line.startswith("#"):
            return m.group(1)
        return "python"

    def run(self, kill=False, *l, **kwargs):
        if kill:
            if self.proc is not None and self.proc.poll() is None:
                self.killed = True
                self.proc.terminate() # send SIGTERM
                self.proc = None
            sublime.message_dialog('Build Cancelled!')
            return

        vars = self.window.extract_variables()
        working_dir = vars['file_path']

        # A lock is used to ensure only one thread is
        # touching the output panel at a time
        with self.panel_lock:
            # Creating the panel implicitly clears any previous contents
            self.panel = self.window.create_output_panel('exec')

            # Enable result navigation. The result_file_regex does
            # the primary matching, but result_line_regex is used
            # when build output includes some entries that only
            # contain line/column info beneath a previous line
            # listing the file info. The result_base_dir sets the
            # path to resolve relative file names against.
            settings = self.panel.settings()
            settings.set(
                'result_file_regex',
                r'^File "([^"]+)" line (\d+) col (\d+)'
            )
            settings.set(
                'result_line_regex',
                r'^\s+line (\d+) col (\d+)'
            )
            settings.set('result_base_dir', working_dir)

            self.window.run_command('show_panel', {'panel': 'output.exec'})

        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            self.proc = None

        args = [ self.detect_version() ]
        # sublime.message_dialog(vars['file_name'])
        args.append(vars['file_name'])
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1" # 及时 print
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=working_dir,
            env=env,
        )
        self.killed = False

        threading.Thread(
            target=self.read_handle,
            args=(self.proc.stdout,)
        ).start()

    def read_handle(self, handle):
        # for line in iter(handle.readline, b''):
        #     self.queue_write(line.decode(self.encoding))
        # handle.close()
        # return

        chunk_size = 2 ** 13
        out = b''
        while True:
            try:
                # sublime.message_dialog('fuck1')
                data = os.read(handle.fileno(), chunk_size)
                # If exactly the requested number of bytes was
                # read, there may be more data, and the current
                # data may contain part of a multibyte char
                out += data
                if len(data) == chunk_size:
                    continue
                if data == b'' and out == b'':
                    raise IOError('EOF')
                # We pass out to a function to ensure the
                # timeout gets the value of out right now,
                # rather than a future (mutated) version
                self.queue_write(out.decode(self.encoding))
                if data == b'':
                    raise IOError('EOF')
                out = b''
            except (UnicodeDecodeError) as e:
                msg = 'Error decoding output using %s - %s'
                self.queue_write(msg  % (self.encoding, str(e)))
                break
            except (IOError):
                if self.killed:
                    msg = 'Cancelled'
                else:
                    msg = 'Finished'
                self.queue_write('\n[%s]' % msg)
                break

    def queue_write(self, text):
        sublime.set_timeout(lambda: self.do_write(text), 1)

    def do_write(self, text):
        with self.panel_lock:
            self.panel.run_command('append', {'characters': text})


# 4 fun
class HelloWorld(sublime_plugin.TextCommand):
    def run(self, edit):
        w = self.view.window()
        p = w.create_output_panel('HelloWorld')
        p.set_read_only(False)
        w.run_command('show_panel', {'panel': 'output.HelloWorld'})
        p.run_command('fuck', {'s': 'blablabla...'})
        p.run_command('append', {'characters': 'blublublublu...'})


class Fuck(sublime_plugin.TextCommand):
    def run(self, edit, s):
        self.view.insert(edit, self.view.size(), s)


class HookCommand(sublime_plugin.EventListener):
    def on_window_command(self, window, command_name, args):
        print('on_window_command:', command_name, args)
        return None

# use everything.exe as backend, real goto anywhere on my computer.
# get https://www.voidtools.com/support/everything/sdk/python/ sdk, rename as es.py, and put it in C:\Users\Administrator\AppData\Roaming\Sublime Text 3\Packages\User\
# D:\Program Files\Sublime Text\Lib\python38\sublime.py
# https://www.sublimetext.com/docs/api_reference.html#sublime.Window.show_quick_panel
class QuickOpenCommand(sublime_plugin.WindowCommand):
    def on_select(self, idx, b):
        # print('result:', idx, b)
        if idx > -1:
            print('selected file:', self.items[idx])
            self.window.open_file(self.items[idx])

    def run(self):
        import platform
        if platform.system() != 'Windows':
            return
        import User.es as es # https://www.voidtools.com/support/everything/sdk/python/

        self.items, t1, t2, t3 = es.es('')
        print('t:', t1, t2, t3)
        # self.window.show_quick_panel(self.items, self.on_select, sublime.WANT_EVENT, -1, None, '')
        sublime_api.window_show_quick_panel(
            self.window.window_id, self.items, self.on_select, None,
            sublime.WANT_EVENT, -1, '')
        # self.window.show_input_panel('test', 'hello', self.hl, self.hl, None)

# window.panels()
# window.find_output_panel('output.exec')







