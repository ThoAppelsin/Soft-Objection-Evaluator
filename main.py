import re, os, shutil
import click
import tarfile
from pathvalidate import sanitize_filepath
import coverage
import edit_distance
from collections import defaultdict
from pylint import lint
from pylint.reporters.text import TextReporter
from io import StringIO
import tempfile
import vulture
import pandas as pd
import itertools
import glob


def tarsextract(tars, outdir):
	if os.path.isdir(outdir):
		if click.confirm(f"Directory '{outdir}' already exists, want to delete it and extract new?", default=False):
			shutil.rmtree(outdir)
		else:
			return

	for tar in tars:
		tf = tarfile.open(tar)
		for file in tf:
			file.name = sanitize_filepath(file.name, replacement_text="_")
		tf.extractall(outdir)


def remove_comments(code):
	return (line if (comment_start := line.find('#')) == -1 else line[:comment_start] for line in code)


def rstrip(code):
	return (line.rstrip() for line in code)


def remove_block_comments(code):
	incomment = False
	commenttype = ''
	for line in code:
		if incomment:
			if line.find(commenttype * 3) >= 0:
				incomment = False
		else:
			l = line
			found_inline_comment = True
			while found_inline_comment:
				found_inline_comment = False
				l = l.lstrip()
				for ctype in ['"', "'"]:
					if l.startswith(ctype * 3):
						cend = l[3:].find(ctype * 3)
						if cend == -1:
							incomment = True
							commenttype = ctype
							break
						else:
							l = l[cend+6:]
							found_inline_comment = True
							break
			if not incomment and l.strip() != '':
				yield line


def remove_empty_lines(code):
	return (line for line in code if line != '')


def join_lines(code):
	rline = ''
	for line in code:
		rline += line
		if rline.endswith('\\'):
			rline = rline[:-1]
		else:
			yield rline
			rline = ''


def sanitize(code):
	return list(join_lines(remove_empty_lines(remove_block_comments(rstrip(remove_comments(code))))))


def get_comment(line):
	start = line.find('#')
	return "" if start == -1 else line[start+1:]


def get_comments(code):
	return (get_comment(line) for line in code)


def extract_user_code(code, codepath):
	bflag = 'DO_NOT_EDIT_ANYTHING_ABOVE_THIS_LINE'
	eflag = 'DO_NOT_EDIT_ANYTHING_BELOW_THIS_LINE'

	stucode = False
	for i, line in enumerate(code):
		comment = get_comment(line)
		if comment:
			if bflag in comment:
				if stucode:
					print(codepath, "is a code with bad flags...")
					yield line
				stucode = True
				continue
			elif eflag in comment:
				if not stucode:
					print(codepath, "is a code with bad flags...")
				stucode = False
				continue
		if stucode:
			yield line


def calculate_edit_distance(old, new):
	sm = edit_distance.SequenceMatcher(old, new)
	return sm.distance()


def run_pylint(filename):
	PERFECT = "\n------------------------------------\nYour code has been rated at 10.00/10\n\n"
	ARGS = ["--disable=all", "--enable=W0104,W0105"]
	outIO = StringIO()
	lint.Run([filename]+ARGS, reporter=TextReporter(outIO), exit=False)

	outIO.seek(0)
	output = outIO.read()

	return output == PERFECT or output


def run_vulture(filename):
	v = vulture.Vulture()
	v.scavenge([filename])
	output = [item.get_report() for item in v.get_unused_code()]
	return output == [] or '\n'.join(output)


def run_tests(code, prepend=''):
	temp = tempfile.NamedTemporaryFile(mode="w", delete=False)
	temp.write('\n'.join(code))
	filename = temp.name
	temp.close()

	pylintres = run_pylint(filename)
	vultureres = run_vulture(filename)

	os.remove(filename)

	if prepend:
		prepend += '-'
	return {prepend + 'pylintres': pylintres, prepend + 'vultureres': vultureres}


def num_colon_follow(code):
	return sum(0 <= line.find(':') < len(line)-1 for line in code)


def num_semicolon(code):
	return '\n'.join(code).count(';')


def num_exec(code):
	return '\n'.join(code).count('exec(')


def get_report(oldpath, newpath, should_sanitize=True):
	with open(oldpath) as oldfile:
		old = extract_user_code(oldfile.readlines(), oldpath)
	with open(newpath) as newfile:
		new = extract_user_code(newfile.readlines(), newpath)
	if should_sanitize:
		old = sanitize(old)
		new = sanitize(new)

	return {
	'edit_distance': calculate_edit_distance(old, new),
	'old-#lines' : len(old),
	'new-#lines': len(new),
	'old-#colonfollow': num_colon_follow(old),
	'new-#colonfollow': num_colon_follow(new),
	'old-#semicolon': num_semicolon(old),
	'new-#semicolon': num_semicolon(new),
	'old-#exec': num_exec(old),
	'new-#exec': num_exec(new)
	} | run_tests(old, 'old') | run_tests(new, 'new')


def main():
	originaltars = [
	"C:/Users/utkan/Downloads/exam888-objection.tar.gz",
	"C:/Users/utkan/Downloads/exam889-objection.tar.gz"]
	correctiontars = [tar for n in range(1,6) for tar in glob.glob(f"C:/Users/utkan/Downloads/m1+/{n}/*.tar.gz")]

	originalsdir = "originals"
	correctionsdir = "corrections"

	tarsextract(originaltars, originalsdir)
	tarsextract(correctiontars, correctionsdir)

	correctiondict = defaultdict(dict)

	for corrdir in os.listdir(correctionsdir):
		qid = corrdir.split('_')[2]
		corrpath = correctionsdir + '/' + corrdir
		for stuid in os.listdir(corrpath):
			correctiondict[stuid][qid] = corrpath + '/' + stuid + '/' + qid + '/src/Main.py'

	reports = []

	for examdir in os.listdir(originalsdir):
		exampath = originalsdir + '/' + examdir
		for stuid in os.listdir(exampath):
			examstupath = exampath + '/' + stuid
			for qid in os.listdir(examstupath):
				examstuqmainpath = examstupath + '/' + qid + '/src/Main.py'
				if qid in correctiondict[stuid]:
					print(stuid, qid)
					reports.append({'user': stuid, 'question': qid} | get_report(examstuqmainpath, correctiondict[stuid][qid]))

	df.DataFrame(report)
	df.to_csv('report.csv')


if __name__ == '__main__':
	main()
	pass
