import re, os, shutil
import click
import tarfile

originaltar = "C:/Users/Utkan Gezer/Downloads/exam888-objection.tar.gz"
correctiontars = [
"C:/Users/Utkan Gezer/Downloads/section151_question1287-objection.tar.gz",
"C:/Users/Utkan Gezer/Downloads/section150_question1286-objection.tar.gz"]

originalsdir = "originals"
correctionsdir = "corrections"

def tarsextract(tars, outdir):
	if os.path.isdir(outdir):
		if click.confirm(f"Directory '{outdir}' already exists, want to delete it and extract new?", default=True):
			shutil.rmtree(outdir)
		else:
			return

	for tar in tars:
		tf = tarfile.open(tar)
		for file in tf:
			file.name = re.sub(r'[\t]', '_', file.name)
		tf.extractall(outdir)

tarsextract([originaltar], originalsdir)
tarsextract(correctiontars, correctionsdir)
