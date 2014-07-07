from os.path import dirname, realpath
import sys
sys.path.append(dirname(realpath(__file__)))

import sublime, sublime_plugin
import re
import time
import os
import threading
import queue
from clang_completion import ClangCompletion

#todo: add autocompletion on-demand
#todo: add "go to definition" all the way down...
#todo: add "fix-it" hints for diagnostics all the way down...

class Substitutor:
	"""this class wraps matches as tab-cyclable fields, to be used in re.sub"""
	def __init__(self, lasti = 0):
		self.i = lasti

	def sub(self, match):
		self.i += 1
		return "${%i:%s}" % (self.i, match.group(0))

class CompletionHandler:
	def __init__(self, view):
		self.filename = view.file_name()
		self.queue = queue.Queue()
		self.lock = threading.Lock()
		self.view = view
		self.project_path = os.path.dirname(self.view.window().project_file_name())
		self.ready = False
		self.diagnostics = []
		self.canceled = False
		self.update_time = None
		self.modification_time = time.time()
		self.completion_server = None
		self.update_timer = None
		sublime.set_timeout_async(self.start, 0)

	def start(self):
		args_dict = {"filename" : self.filename}
		try:
			project_data = self.view.window().project_data()
			settings = project_data.get("clang_completion", {})
			if "server_call" in settings:
				args_dict["server_call"] = settings["server_call"]
			if "args" in settings:
				args_dict["args"] = [self.__process_argument(arg) for arg in settings["args"]]
		except Exception as e:
			print(e)
		# lower the completion delay, so we wont interrupt typing
		if self.view.settings().has("auto_complete_delay"):
			auto_complete_delay = max(250, self.view.settings().get("auto_complete_delay"))
			self.view.settings().set("auto_complete_delay", auto_complete_delay)
			print("set auto_complete_delay for '%s' to" % self.filename, auto_complete_delay)
		self.view.set_status("clang", "clang: starting")
		self.completion_server = ClangCompletion(**args_dict)
		self.ready = True
		self.__update()

	def handle_modified(self):
		self.modification_time = time.time()
		if self.update_timer:
			self.update_timer.cancel()
		self.update_timer = threading.Timer(0.5, self.__update)
		self.update_timer.start()

	def complete_at(self, location):
		contents = self.view.substr(sublime.Region(0, self.view.size()))
		(row, column) = self.view.rowcol(location)
		completions = self.completion_server.complete(row, column, unsaved_source = contents)
		return ([self.__convert_completion(completion) for completion in completions], sublime.INHIBIT_EXPLICIT_COMPLETIONS)

	def __process_argument(self, arg):
		return arg.replace("${project_path}", self.project_path)

	def __update(self):
		if self.update_time and self.update_time >= self.modification_time:
			return
		self.update_time = time.time()
		self.__update_diagnostics()

	def __update_diagnostics(self):
		self.view.set_status("clang", "clang: updating diagnostics")
		filename = self.view.file_name()
		contents = self.view.substr(sublime.Region(0, self.view.size()))
		diagnostics = self.completion_server.check(unsaved_source = contents)
		error_regions = []
		warning_regions = []
		self.diagnostics = []
		for diagnostic in diagnostics:
			if diagnostic.get("file") == filename and "row" in diagnostic and "column" in diagnostic:
				point = self.view.text_point(diagnostic["row"] - 1, diagnostic["column"])
				region = self.view.word(point)
				if "error" in diagnostic.get("type"):
					error_regions.append(region)
				else:
					warning_regions.append(region)
				self.diagnostics.append({"region" : region, "info" : diagnostic})
		self.view.add_regions("clang_warnings", warning_regions, "comment", "circle", sublime.DRAW_OUTLINED)
		self.view.add_regions("clang_errors", error_regions, "invalid", "circle", sublime.DRAW_OUTLINED)
		self.view.set_status("clang", "clang: %d errors and %d warnings" % (len(error_regions), len(warning_regions)))

	def __convert_completion(self, completion):
		label = completion[0]
		if len(completion) == 2:
			# todo: what about optionals?
			text = completion[1]
			substitutor = Substitutor(0)
			text = re.sub("\<\#.*?\#\>", substitutor.sub, text)			
			text = re.sub("\[\#.*?\#\]", "", text).strip()
		else:
			text = completion[0]
		return (label + "\tclang", text)

class ClangCompletionPlugin(sublime_plugin.EventListener):
	def __init__(self):
		print("initializing ClangCompletion plugin")
		self.handlers = {}

	def on_activated(self, view):
		self.on_load(view)

	def on_load(self, view):
		if view.file_name().split(".")[-1] in ["c", "cpp", "hpp", "h"] \
		and view.window().project_data().get("clang_completion", {}).get("enabled") \
		and view.file_name() not in self.handlers:
			self.handlers[view.file_name()] = CompletionHandler(view)

#	def on_post_save(self, view):
#		handler = self.handlers.get(view.file_name())
#		if handler:
#			handler.update_source()

	def on_close(self, view):
		filename = view.file_name()
		if filename in self.handlers:
			del self.handlers[filename]

	def on_selection_modified(self, view):
		filename = view.file_name()
		handler = self.handlers.get(filename)
		found_diagnostic = None
		if handler:
			selection = view.sel()
			if len(selection) == 1:
				for diagnonstic in handler.diagnostics:
					if diagnonstic["region"].intersects(selection[0]):
						found_diagnostic = diagnonstic
						break
		if found_diagnostic:
			text = found_diagnostic["info"].get("type", "diagnostic") + ": " + found_diagnostic["info"]["text"]
			view.set_status("diagnonstic", text)
		else:
			view.erase_status("diagnonstic")

	def on_modified(self, view):
		handler = self.handlers.get(view.file_name())
		if handler:
			handler.handle_modified()
			self.on_selection_modified(view)

	def on_query_completions(self, view, prefix, locations):
		handler = self.handlers.get(view.file_name())
		if len(locations) == 1 and handler and handler.ready:
			return handler.complete_at(locations[0])

# this works around the fact that currently on_activated is not called upon startup
# this is timing dependent, so probably will break in certain cases
# hope upstread fixes this soon...
def plugin_loaded():
	sublime.set_timeout(force_active, 1)

def force_active():
	import sublime_api
	view_id = sublime_api.window_active_view(sublime_api.active_window())
	sublime_plugin.on_activated(view_id)