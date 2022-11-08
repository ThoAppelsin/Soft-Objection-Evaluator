import re, os, shutil
import click
import tarfile
from pathvalidate import sanitize_filepath
import coverage
import editdistance
from collections import defaultdict
from pylint import lint
from pylint.reporters.text import TextReporter
from io import StringIO
import tempfile
import vulture
import pandas as pd


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


def edit_distance(old, new):
	return editdistance.eval(old, new)


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
		old = oldfile.readlines()
	with open(newpath) as newfile:
		new = newfile.readlines()
	if should_sanitize:
		old = sanitize(old)
		new = sanitize(new)

	return {
	'edit_distance': edit_distance(old, new),
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
	"C:/Users/Utkan Gezer/Downloads/exam888-objection.tar.gz",
	"C:/Users/Utkan Gezer/Downloads/exam889-objection.tar.gz"]
	correctiontars = [tar for n in range(1,6) for tar in os.listdir(f"C:/Users/utkan/Downloads/m1+/{n}")]

	originalsdir = "originals"
	correctionsdir = "corrections"

	tarsextract(originaltars, originalsdir)
	tarsextract(correctiontars, correctionsdir)

	correctiondict = defaultdict(dict)

	for corrdir in os.listdir(correctionsdir):
		qid = corrdir.split('_')[2]
		corrpath = correctionsdir + '/' + corrdir
		for stuid in os.listdir(corrpath):
			correctiondict[stuid][qid] = corrpath + '/' + stuid + '/' + qid + '/src_separated/Main.py_1_true.txt'

	reports = []

	for examdir in os.listdir(originalsdir):
		exampath = originalsdir + '/' + examdir
		for stuid in os.listdir(exampath):
			examstupath = exampath + '/' + stuid
			for qid in os.listdir(examstupath):
				examstuqmainpath = examstupath + '/' + qid + '/src_separated/Main.py_1_true.txt'
				if qid in correctiondict[stuid]:
					reports.append({'user': stuid, 'question': qid} | get_report(examstuqmainpath, correctiondict[stuid][qid]))

	df.DataFrame(report)
	df.to_csv('report.csv')


if __name__ == '__main__':
	main()
