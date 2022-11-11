import re, os, shutil
import click
import tarfile
from pathvalidate import sanitize_filepath
import coverage
import edit_distance
from collections import defaultdict
from pylint.reporters.text import TextReporter
from io import StringIO
import tempfile
import vulture
import pandas as pd
import itertools
import glob
from pathlib import Path
from contextlib import redirect_stderr
from alive_progress import alive_bar


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
	return (line.rstrip(" \t\n\r;") for line in code)


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


def extract_user_code(code):
	bflag = 'DO_NOT_EDIT_ANYTHING_ABOVE_THIS_LINE'
	eflag = 'DO_NOT_EDIT_ANYTHING_BELOW_THIS_LINE'

	flags = (True if bflag in c else False if eflag in c else None for c in get_comments(code))
	flags = [(i, f) for i, f in enumerate(flags) if f != None]
	goodflags = all(x[1] for x in flags[::2]) and not any(x[1] for x in flags[1::2]) and len(flags) % 2 == 0

	def sturanges():
		rangestart = -1
		for i, f in flags:
			if rangestart == -1:
				if f:
					rangestart = i + 1
			else:
				if not f:
					yield (rangestart, i)
					rangestart = -1

	return [line for r in sturanges() for line in code[r[0]:r[1]]], goodflags


def calculate_edit_distance(old, new):
	sm = edit_distance.SequenceMatcher(old, new)
	return sm.distance()


def run_pylint(filename):
	from pylint import lint

	PERFECT = "\n------------------------------------\nYour code has been rated at 10.00/10\n\n"
	ARGS = ["--disable=all", "--enable=W0104,W0105"]
	outIO = StringIO()
	lint.Run([filename]+ARGS, reporter=TextReporter(outIO), exit=False)

	outIO.seek(0)
	output = outIO.read()

	return output == PERFECT or output == "" or output


def run_vulture(filename):
	v = vulture.Vulture()
	with redirect_stderr(StringIO()) as f:
		v.scavenge([filename])
	errout = f.getvalue()
	output = [errout] if errout else []
	output += [item.get_report() for item in v.get_unused_code()]
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


flawless = {
	'old-#colonfollow': 0,
	'new-#colonfollow': 0,
	'old-#semicolon': 0,
	'new-#semicolon': 0,
	'old-#exec': 0,
	'new-#exec': 0,
	'old-goodflags': True,
	'new-goodflags': True,
	'old-pylintres': True,
	'old-vultureres': True,
	'new-pylintres': True,
	'new-vultureres': True
	}


def get_report(oldpath, newpath, should_sanitize=True):
	with open(oldpath) as oldfile:
		old, oldgoodflags = extract_user_code(oldfile.readlines())
	with open(newpath) as newfile:
		new, newgoodflags = extract_user_code(newfile.readlines())
	if should_sanitize:
		old = sanitize(old)
		new = sanitize(new)

	return len(new) > 0 and {
	'edit_distance': calculate_edit_distance(old, new),
	'old-#lines' : len(old),
	'new-#lines': len(new),
	'old-#colonfollow': num_colon_follow(old),
	'new-#colonfollow': num_colon_follow(new),
	'old-#semicolon': num_semicolon(old),
	'new-#semicolon': num_semicolon(new),
	'old-#exec': num_exec(old),
	'new-#exec': num_exec(new),
	'old-goodflags': oldgoodflags,
	'new-goodflags': newgoodflags
	} | run_tests(old, 'old') | run_tests(new, 'new')


def main():
	downloads = Path.home() / "Downloads"
	originaltars = [
	downloads / "exam888-objection.tar.gz",
	downloads / "exam889-objection.tar.gz"]
	correctiontars = [tar for n in range(1,6) for tar in (downloads / f"m1+/{n}").glob("*.tar.gz")]

	originalsdir = "originals"
	correctionsdir = "corrections"

	tarsextract(originaltars, originalsdir)
	tarsextract(correctiontars, correctionsdir)

	correctiondict = defaultdict(dict)

	for corrdir in os.listdir(correctionsdir):
		_, sid, qid = corrdir.split('_')
		corrpath = correctionsdir + '/' + corrdir
		for stuid in os.listdir(corrpath):
			correctiondict[stuid][qid] = {'path': corrpath + '/' + stuid + '/' + qid + '/src/Main.py', 'section': sid}

	reports = []

	with alive_bar(len(glob.glob(originalsdir + "/*/*/*"))) as bar:
		for examdir in os.listdir(originalsdir):
			examid = examdir.split('_')[1]
			exampath = originalsdir + '/' + examdir
			for stuid in os.listdir(exampath):
				examstupath = exampath + '/' + stuid
				for qid in os.listdir(examstupath):
					examstuqmainpath = examstupath + '/' + qid + '/src/Main.py'
					if qid in correctiondict[stuid]:
						corrstuqmainpath = correctiondict[stuid][qid]['path']
						report = get_report(examstuqmainpath, corrstuqmainpath)
						if report:
							reports.append({
								'user': stuid,
								'old': f'=HYPERLINK("{examstuqmainpath}")',
								'new': f'=HYPERLINK("{corrstuqmainpath}")',
								# 'question': qid,
								# 'section': correctiondict[stuid][qid]['section'],
								# 'exam': examid
								} | report)

					bar()

	df = pd.DataFrame(reports)
	df['needs_inspection'] = df.apply(lambda r: ', '.join(c for c in flawless if flawless[c] != r[c]), axis=1) # (df[flawless.keys()] != flawless.values()).any(axis=1)
	df = df.drop(columns=[c for c, fless in flawless.items() if all(df[c] == fless)])
	df.to_csv('report.csv')
	return df


if __name__ == '__main__':
	df = main()
