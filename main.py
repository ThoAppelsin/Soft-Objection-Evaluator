import re, os, shutil
import click
import tarfile
from pathvalidate import sanitize_filepath
import coverage

originaltars = [
"C:/Users/Utkan Gezer/Downloads/exam888-objection.tar.gz",
"C:/Users/Utkan Gezer/Downloads/exam889-objection.tar.gz"]
correctiontars = [
"C:/Users/Utkan Gezer/Downloads/section151_question1287-objection.tar.gz",
"C:/Users/Utkan Gezer/Downloads/section150_question1286-objection.tar.gz"]

originalsdir = "originals"
correctionsdir = "corrections"

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

tarsextract(originaltars, originalsdir)
tarsextract(correctiontars, correctionsdir)

# pylint --disable=all --enable=W0105 .\Corrected.py

