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
    def run(self, edit, text = None):
        if not text:
            self.view.window().show_input_panel("input start and step:", "start:1, step:1", lambda text: self.view.run_command('insert_number', {"text": text}), None, None)
            return

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
    def run(self, edit):
        pre_row = -1
        pos_max_x = 0.0
        for region in self.view.sel():
            (row,col) = self.view.rowcol(region.begin())
            if row == pre_row:
                sublime.error_message(u"不能在同一行选中两个位置！！")
                return
            pre_row = row
            point_begin = region.begin() # region.end()
            vec_pos = self.view.text_to_layout(point_begin)
            if vec_pos[0] > pos_max_x:
                print(vec_pos[0])
                pos_max_x = vec_pos[0]

        print('pos_max_x:', pos_max_x)
        for i in range(len(self.view.sel())):
            region = self.view.sel()[i]
            pos_cur_x = self.view.text_to_layout(region.begin())[0]
            if pos_cur_x >= pos_max_x: continue
            print("pos_cur_x:", pos_cur_x)
            while pos_cur_x < pos_max_x:
                self.view.insert(edit, region.begin(), " ")
                region = self.view.sel()[i]
                pos_cur_x = self.view.text_to_layout(region.begin())[0]
            print("pos_new_x:", self.view.text_to_layout(region.begin()))

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
    def on_pre_save(self, view):
        if not view.file_name().endswith('Makefile'):
            view.run_command('my_expand_tabs')
    def on_load(self, view):
        print('on_load:', view.encoding())
        if view.encoding() == 'Undefined':
            return
        if view.encoding().lower() == 'utf-8':
            return
        try:
            # GB18030 与 GB2312 和 GBK 兼容
            with open(view.file_name(), 'r', encoding='GB18030') as f:
                text = f.read(1024)
                f_tmp = open(view.file_name()+'.utf8~', 'w', encoding='utf-8')
                while text:
                    f_tmp.write(text)
                    text = f.read(1024)
                f_tmp.close()
            os.replace(view.file_name()+'.utf8~', view.file_name())
        except Exception as e:
            print(e)


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
    def on_hl(self, idx):
        self.window.open_file(self.items[idx], sublime.TRANSIENT)

    def run(self):
        import platform
        if platform.system() != 'Windows':
            return
        import User.es as es # https://www.voidtools.com/support/everything/sdk/python/

        self.items, t1, t2, t3 = es.es('*.h|*.c|*.cc|*.cpp|*.cxx|*.lua|*.py|*.conf|*.txt|*.md|*.xml|*.sh|')
        print('t:', t1, t2, t3)
        # self.window.show_quick_panel(self.items, self.on_select, sublime.WANT_EVENT, -1, None, '')
        sublime_api.window_show_quick_panel(
            self.window.window_id, self.items, self.on_select, self.on_hl,
            sublime.WANT_EVENT, -1, '')
        # self.window.show_input_panel('test', 'hello', self.hl, self.hl, None)

# window.panels()
# window.find_output_panel('output.exec')


class QuitFindResultsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        print(self.view.name(), self.view.file_name())

        if self.view.file_name():
            if self.view.file_name().endswith('.sublime-keymap') or self.view.file_name().endswith('.sublime-settings'):
                self.view.close()
                return

        if self.view.name() == 'Find Results':
            self.view.close()
            return

        # default [escape]
        self.view.window().run_command('cancel')


class MyExpandTabsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view

        # reversed 是为了保证 expandtabs 之后不影响后续需要 expandtabs 的 str
        for region in reversed(view.lines(sublime.Region(0, view.size()))):
            src = view.substr(region)
            dst = src.expandtabs(int(view.settings().get('tab_size', 4)))
            if src != dst:
                view.replace(edit, region, dst)

# pip install the package to sublime directory, then we can import it in this plugin file
class PipInstallCommand(sublime_plugin.TextCommand):
    def run(self, edit, package=None):
        import sys, os

        # sublime.executable_path()
        # pkg_path = sublime.packages_path()

        version = sys.version_info
        p = [p for p in sys.path if f'Lib/python{version.major}{version.minor}' in p and 'Sublime Text ' in p]
        p = p[0]

        if not package:
            self.view.window().show_input_panel("pip install ", "", lambda pkg: self.view.run_command('pip_install', {"package": pkg}), None, None)
            return

        self.view.window().run_command('exec', {'cmd': ['pip3', 'install', package, '--target', p, ], })

        # print(f"pip3 install --target '{p}' --upgrade {package}")
        # res = os.popen(f"pip3 install --target '{p}' --upgrade {package}").read()
        # print(res)

def auto_generate_sublime_commands():

    def isclass(o):
        return isinstance(o, type)

    def get_name_from_cls(t, cls):
        sep = '_' if t == 'command' else ' '
        clsname = cls.__name__
        name = clsname[0].lower()
        last_upper = False
        for c in clsname[1:]:
            if c.isupper() and not last_upper:
                name += sep
                name += c.lower()
            else:
                name += c
            last_upper = c.isupper()
        if name.endswith(f"{sep}command"):
            name = name[0:-8]
        return name

    # cwd = os.getcwd()
    fdir = os.path.dirname(__file__)
    basename = os.path.basename(__file__)
    cur_plugin_name = os.path.splitext(basename)[0]
    cfg = os.path.join(fdir, f'{cur_plugin_name}.sublime-commands')
    if not os.path.isfile(cfg):
        pathlib.Path(cfg).touch()

    commands = []
    with open(cfg, 'r') as f:
        commands = json.loads(f.read() or "[]")

    kv = {k['command'] : True for k in commands}

    g = globals()

    dirty = False

    for k in [x for x in g]:
        v = g[k]
        if not isclass(v):
            continue
        if v.__module__ != __name__:
            continue
        if all([
                not issubclass(v, sublime_plugin.ApplicationCommand),
                not issubclass(v, sublime_plugin.WindowCommand),
                not issubclass(v, sublime_plugin.TextCommand)
            ]):
            continue

        if get_name_from_cls('command', v) in kv:
            continue

        commands.append({
            'command': get_name_from_cls('command', v),
            'caption': f'{cur_plugin_name}: {get_name_from_cls("caption", v)}',
        })

        dirty = True

    if dirty:
        with open(cfg, 'w') as f:
            f.write(json.dumps(commands, indent=4)) # indent for pretty dump


auto_generate_sublime_commands()
