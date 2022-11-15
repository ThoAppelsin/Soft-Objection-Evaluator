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
from alive_progress import alive_bar, alive_it
import tokenize
from time import sleep
import mergedeep
import ast
import warnings


def tarsextract(tars, outdir):
	if os.path.isdir(outdir):
		if click.confirm(f"Directory '{outdir}' already exists, want to delete it and extract new?", default=False):
			shutil.rmtree(outdir)
		else:
			return

	os.mkdir(outdir)
	for tar in tars:
		tf = tarfile.open(tar)
		for file in tf:
			file.name = sanitize_filepath(file.name, replacement_text="_")
		tf.extractall(outdir)


def join_triplequote_strings(code):
	rline = ''
	inquotes = False
	for line in code:
		rline += line
		qactivity = True
		while qactivity:
			qactivity = False
			if inquotes:
				qend = line.find(inquotes)
				if qend != -1:
					line = line[qend+len(inquotes):]
					inquotes = False
					qactivity = True
			else:
				qstart = sorted((s, q) for q in ["'''", '"""'] if (s := line.find(q)) != -1)
				if qstart:
					s, q = qstart[0]
					line = line[s+len(q):]
					inquotes = q
					qactivity = True
		if inquotes:
			if not rline.endswith('\\'):
				rline += '\\n'
		else:
			yield rline
			rline = ''


def comment_index(line):
	try:
		comments = [x for x in tokenize.generate_tokens(StringIO(line).readline) if x[0] == tokenize.COMMENT]
		return comments[0][2][1] if len(comments) == 1 else -1
	except tokenize.TokenError as e:
		if line.find('#') != -1:
			sleep(10)
			print("We have a # and:", str(e))
		return -1


def join_lines(code):
	rline = ''
	for line in code:
		rline += line
		if comment_index(line) == -1 and rline.endswith('\\'):
			rline = rline[:-1]
		else:
			yield rline
			rline = ''


# def remove_triplequote_comments(code):
# 	incomment = False
# 	commenttype = ''
# 	for line in code:
# 		if incomment:
# 			if line.find(commenttype * 3) >= 0:
# 				incomment = False
# 		else:
# 			l = line
# 			found_inline_comment = True
# 			while found_inline_comment:
# 				found_inline_comment = False
# 				l = l.lstrip()
# 				for ctype in ['"', "'"]:
# 					if l.startswith(ctype * 3):
# 						cend = l[3:].find(ctype * 3)
# 						if cend == -1:
# 							incomment = True
# 							commenttype = ctype
# 							break
# 						else:
# 							l = l[cend+6:]
# 							found_inline_comment = True
# 							break
# 			if not incomment and l.strip() != '':
# 				yield line


def remove_quote_comments(code):
	for line in code:
		l = line.strip()
		repeat = True
		while repeat:
			repeat = False
			for q in ["'''", '"""', "'", '"']:
				if l.startswith(q):
					qend = l.find(q, len(q))
					if qend == -1:
						sleep(10)
						print(f"Quotes left unclosed! Full line: >{line}< and rest of the line >{l}")
						break
					l = l[qend+len(q):].lstrip()
					repeat = True
					break
		if l != '':
			yield line


def remove_comments(code):
	return (line if (ci := comment_index(line)) == -1 else line[:ci] for line in code)


def rstrip(code):
	return (line.rstrip(" \t\n\r;") for line in code)


def remove_empty_lines(code):
	return (line for line in code if line != '')


def sanitize(code):
	return list(remove_empty_lines(rstrip(remove_comments(remove_quote_comments(join_lines(join_triplequote_strings(code)))))))


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


def run_pylint(testfpath):
	from pylint import lint

	PERFECT = "\n------------------------------------\nYour code has been rated at 10.00/10\n\n"
	ARGS = ["--disable=all", "--enable=W0104,W0105"]
	outIO = StringIO()
	lint.Run([testfpath]+ARGS, reporter=TextReporter(outIO), exit=False)

	outIO.seek(0)
	output = outIO.read()

	return output == PERFECT or output == "" or output


def prepare_vulture_whitelist(srcpath):
	wlpath = srcpath.parent / (srcpath.stem + '-whitelist.py')

	v = vulture.Vulture()
	v.scavenge([srcpath])
	with open(wlpath, 'w') as wlf:
		print('\n'.join(item.get_whitelist_string() for item in v.get_unused_code()), file=wlf)

	return wlpath


def run_vulture(testfpath, vulturewlpath):
	v = vulture.Vulture()
	with redirect_stderr(StringIO()) as f:
		v.scavenge([testfpath, vulturewlpath])
		errout = f.getvalue()
	vulpath = vulture.utils.format_path(Path(testfpath).resolve())
	invalid_syntax_regex = str(vulpath).replace('\\', '\\\\') + r":\d+: invalid syntax at .*"
	errout = '\n'.join(l for l in errout.splitlines() if not re.match(invalid_syntax_regex, l))
	output = [errout] if errout else []
	output += [item.get_report() for item in v.get_unused_code()]
	return output == [] or '\n'.join(output)


def run_tests(code, vulturewlpath, prepend=''):
	temp = tempfile.NamedTemporaryFile(mode="w", delete=False)
	temp.write('\n'.join(code))
	testfpath = temp.name
	temp.close()

	pylintres = run_pylint(testfpath)
	vultureres = run_vulture(testfpath, vulturewlpath)

	os.remove(testfpath)

	if prepend:
		prepend += '-'
	return {prepend + 'pylint': pylintres, prepend + 'vultur': vultureres}


def num_colon_follow(code):
	return sum(0 <= line.find(':') < len(line)-1 for line in code)


def num_semicolon(code):
	return '\n'.join(code).count(';')


def num_comma(code):
	return len(re.findall(r""",\s*(?!"|'|\s|end\s*=)""", '\n'.join(code)))


def num_exec(code):
	return '\n'.join(code).count('exec(')


class MultiAssignCountVisitor(ast.NodeVisitor):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.count = 0

	def visit_Assign(self, node):
		if len(node.targets) > 1 or any(type(t) is ast.Tuple for t in node.targets):
			self.count += 1


def num_multi_assign(code):
	macv = MultiAssignCountVisitor()
	ap = ast.parse('\n'.join(code))
	macv.visit(ap)
	return macv.count


def num_multi_assign_naive(code):
	return sum(0 if (eqidx := line.find('=')) == -1 else line[:eqidx].count(',') for line in code)


flawless = {
	'old-#colfol': 0,
	'old-#semcol': 0,
	'old-#comma': 0,
	'old-#exec': 0,
	# 'old-#mulas': 0,
	'old-flagOK': True,
	'old-pylint': True,
	'old-vultur': True,
	'new-#colfol': 0,
	'new-#semcol': 0,
	'new-#comma': 0,
	'new-#exec': 0,
	# 'new-#mulas': 0,
	'new-flagOK': True,
	'new-pylint': True,
	'new-vultur': True
	}


def get_report(oldpath, newpath, vulturewlpath, should_sanitize=True):
	with open(oldpath) as oldfile:
		oldfull = oldfile.read().splitlines()
		old, oldgoodflags = extract_user_code(oldfull)
	with open(newpath) as newfile:
		newfull = newfile.read().splitlines()
		new, newgoodflags = extract_user_code(newfull)
	if should_sanitize:
		oldfull = sanitize(oldfull)
		newfull = sanitize(newfull)
		old = sanitize(old)
		new = sanitize(new)

	return len(new) > 0 and {
	'edit_dist': calculate_edit_distance(old, new),
	'old-#lines' : len(old),
	'old-#colfol': num_colon_follow(old),
	'old-#semcol': num_semicolon(old),
	'old-#comma': num_comma(old),
	'old-#exec': num_exec(old),
	# 'old-#mulas': num_multi_assign_naive(old),
	'old-flagOK': oldgoodflags,
	} | run_tests(oldfull, vulturewlpath, 'old') | {
	'new-#lines': len(new),
	'new-#colfol': num_colon_follow(new),
	'new-#semcol': num_semicolon(new),
	'new-#comma': num_comma(new),
	'new-#exec': num_exec(new),
	# 'new-#mulas': num_multi_assign_naive(new),
	'new-flagOK': newgoodflags
	} | run_tests(newfull, vulturewlpath, 'new')


def subreport(report, tag):
	return {k: v for k, v in report.items() if (k.startswith(f"{tag}-") if tag else "-" not in k)}


def collect_gradebook(path, suffix):
	with warnings.catch_warnings(record=True):
		gradebook = pd.read_excel(path, header=1)

	gradecolumns = [c for c in gradebook.columns if c.startswith('Total')]

	if len(qlists := gradebook["Question Id List"].unique()) != 1:
		print(f"Gradebook {path.name} contains multiple Question Id Lists: {qlists}")

	return ({'user': f"user{r['User ID']}", 'qid': f"question{q}", f'grade-{suffix}': g}
			for i, r in gradebook.iterrows()
			for q, g in zip(str(r["Question Id List"]).split(", "), r[gradecolumns]))


# def main():
coursehome = Path.home() / "Downloads/cmpe150fall2022"
mthome = coursehome / "mt1"

questiontars = mthome.glob("mt1questions/*.tar.gz")
originaltars = mthome.glob("mt1originals/*.tar.gz")
correctiontars = mthome.glob("mt1corrections/*/*.tar.gz")

questionsdir = Path("questions")
originalsdir = Path("originals")
correctionsdir = Path("corrections")

# EXTRACT TARS
tarsextract(questiontars, questionsdir)
tarsextract(originaltars, originalsdir)
tarsextract(correctiontars, correctionsdir)

# PREPARE VULTURE WHITELISTS
vulturewldict = {qdir.name : prepare_vulture_whitelist(qdir / 'src/Main.py') for qdir in questionsdir.iterdir()}

# PREPARE POINTERS TO CORRECTIONS
correctiondict = mergedeep.merge({}, *({ cpath.parts[-4] : { cpath.parts[-3] : { 'path': cpath, 'section': cpath.parts[-5].split('_')[1] } } }
										for cpath in correctionsdir.glob("*/*/*/src/Main.py")))

# COLLECT ORIGINAL GRADES
originalgradebooks = mthome.glob("mt1originals/*.xlsx")
originaldf = pd.DataFrame(itertools.chain(*(collect_gradebook(gb, 'original') for gb in originalgradebooks))).set_index(['user', 'qid'])

# COLLECT CORRECTION GRADES
correctiongradebooks = mthome.glob("mt1corrections/*/*.xlsx")
correctiondf = pd.DataFrame(itertools.chain(*(collect_gradebook(gb, 'correction') for gb in correctiongradebooks))).set_index(['user', 'qid'])

# COLLECT STUDENT INFO
studentinfodf = pd.read_excel(coursehome / 'studentinfo.xlsx')
studentinfodf['user'] = ['user' + str(x) for x in studentinfodf['user']]
studentinfodf = studentinfodf.set_index('user')
studentinfodf.columns = pd.MultiIndex.from_product([['INFO'], studentinfodf.columns])

# PREPARE REPORT
reports = []

qidtoqnum = {
	'question1291': 'q1',
	'question1292': 'q1',
	'question1293': 'q2',
	'question1294': 'q2',
	'question1295': 'q3',
	'question1296': 'q3'
	}

for opath in (bar := alive_it(list(originalsdir.glob("*/*/*/src/Main.py")))):
	examid = opath.parts[-5].split('_')[1]
	stuid = opath.parts[-4]
	qid = opath.parts[-3]

	bar.title(f'on {stuid}-{qid}')

	if qid in correctiondict[stuid]:
		cpath = correctiondict[stuid][qid]['path']
		report = get_report(opath, cpath, vulturewldict[qid])
		if report:
			reports.append({
				'user': stuid,
				# 'qnum': qidtoqnum[qid],
				'qid': qid,
				# 'sect': correctiondict[stuid][qid]['section'],
				# 'exam': examid,
				'old': f'=HYPERLINK("{opath}")'
				} | subreport(report, 'old') | {
				'new': f'=HYPERLINK("{cpath}")'
				} | subreport(report, 'new') | subreport(report, False))

reportdf = pd.DataFrame(reports)
reportdf['ratio'] = 1 - reportdf['edit_dist'] / reportdf[['old-#lines', 'new-#lines']].max(axis=1)
reportdf['inspect'] = reportdf.apply(lambda r: ', '.join(c for c in flawless if flawless[c] != r[c]), axis=1)

reportdf[( c for c in reportdf.columns if c not in ['qid', 'sect', 'exam'] and (c not in flawless or (reportdf[c] != flawless[c]).any()) )].to_excel('report_corrections.xlsx')

# reportdf.pivot(index="user", columns="qnum").swaplevel(0, 1, axis=1).sort_index(1)['q2']

df = originaldf.join(correctiondf).join(reportdf.set_index(['user', 'qid'])).reset_index(1)
df['qnum'] = df['qid'].apply(lambda x: qidtoqnum[x])
df['grade-new'] = pd.concat([df['grade-original'], df['grade-correction'] * df['ratio']], axis=1).max(axis=1)

qnums = df['qnum'].unique()
df = df.pivot(columns='qnum').swaplevel(0, 1, axis=1).sort_index(axis=1)
df[('TOTAL', 'ORIGINAL')] = pd.concat((df[(qnum, 'grade-original')] for qnum in qnums), axis=1).mean(axis=1)
df[('TOTAL', 'NEW')] = pd.concat((df[(qnum, 'grade-new')] for qnum in qnums), axis=1).mean(axis=1)
df[('TOTAL', 'DELTA')] = df[('TOTAL', 'NEW')] - df[('TOTAL', 'ORIGINAL')]
# df[('INFO', 'STUDENT ID')] = [studentinfodf.loc[user, 'studeintID'] if user in studentinfodf.index else 'MISSING' for user in df.index]
df = df.join(studentinfodf)
df.to_excel('report_full.xlsx')

# 	return df, reportdf


# # if __name__ == '__main__':
# df, reportdf = main()
