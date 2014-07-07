import subprocess
import os
import struct
import sys

class ClangCompletion:
	"""this is a thin convenience wrapper around the clang-complete exe"""

	def __init__(self, filename, args = [], server_call = ["/usr/local/bin/clang-complete"]):
		self.filename = filename
		print("starting completion for '%s'" % self.filename)
		myenv = os.environ.copy()
		myenv["DYLD_LIBRARY_PATH"] = "/usr/local/opt/llvm/lib"
		self.completion_server = subprocess.Popen(args = server_call + args + [filename],
			                                      stdin = subprocess.PIPE,
			                                      stdout = subprocess.PIPE,
                                                  env = myenv)

	def update_args(self, args):
		self.__write_to_server("\n".join(["num_args:%d" % len(args) + args] + "\n"))

	def update_source(self, contents):
		self.__write_to_server("SOURCEFILE\n")
		self.__push_source(contents)

	def complete(self, row, column, unsaved_source = None):
		self.__write_to_server("COMPLETION\nrow:%d\ncolumn:%d\n" % (row, column))
		self.__push_source(unsaved_source)
		response = self.__read_response()
		completions = [self.__parse_completion(line) for line in response.strip().split("\n")]
		return completions

	def check(self, unsaved_source = None):
		self.__write_to_server("SYNTAXCHECK\n")
		self.__push_source(unsaved_source)
		response = self.__read_response().strip()
		if not response: return []
		diagnostics = [self.__parse_diagnostic(line) for line in response.strip().split("\n")]
		return diagnostics

	def __parse_completion(self, line):
		parts = line[len("COMPLETION: "):].split(" : ")
		return parts

	def __parse_diagnostic(self, line):
		parts = [part for part in line.split(":")]
		if len(parts) == 2:
			return {"type" : parts[0].strip(), "text" : parts[1].strip()}
		elif len(parts) > 4:
			prefix_len = sum([len(part) for part in parts[:4]]) + 4
			remainder = line[prefix_len:].strip()
			return {"file" : parts[0], "row" : int(parts[1]), "column" : int(parts[2]), "type" : parts[3].strip(), "text" : remainder}
		else:
			return {"text" : line}

	def __read_response(self):
		fstr = ''
		while not fstr or fstr[-1] != "$":
			fstr += self.completion_server.stdout.read(int(100000000)).decode("UTF-8")
		return fstr[:-1]
	
	def __write_to_server(self, data):
		self.completion_server.stdin.write(bytes(data, 'UTF-8'))

	def __push_source(self, content = None):
		if not content:
			with open(self.filename, 'r') as content_file:
				content = content_file.read()    	 
		self.__write_to_server("source_length:%d\n" % len(content))
		self.__write_to_server(content)

	def __del__(self):
		print("shutting down completion for '%s'" % self.filename)
		self.__write_to_server("SHUTDOWN\n")
