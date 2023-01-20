# Soft-Objection Evaluator

A piece of software to evaluate specific type of objections where the aim is to provide partial grades to submitted imperfect codes by their closeness to being perfect.


## Workflow

1. Students are presented with a copy of their original submissions
1. Students are asked to correct their imperfect submissions to being perfect with as few of a change as possible
1. Corrections are graded
1. Evaluator script then
  1. normalizes the original and correction submissions,
  1. gathers everything that it deems fishy in corrections (also the originals),
  1. measures how close the originals were to their corrections,
  1. calculates a new grade by this closeness


## The good

This (effectively and ideally) achieves the following:
- **Standardized fairness --** Each submission receives a grade by their closeness to being perfect.
- **Learning from mistakes --** Students are motivated towards revisiting their imperfect code, locating their mistakes, and fixing them up.
- **Maximum parallelism --** The bulk of the task is to prepare the corrections, and that task is distributed across all the students.

The script also runs in under 20 seconds, start-to-finish, to evaluate over 200 corrections.


## The bad

There are, however, some problems:
- **Semantically ignorant evaluator --** The evaluator script, with today's technology, is merely checking closeness by some sequence distance metric (e.g., Levenshtein distance). Whether it be per line or per token, it counts all differences as the same, while semantically they may not be the same.
- **Calculating students --** Knowing the partial grading workflow, students tend to heavily compress their corrections, sometimes insincerely so as evidenced by the disparity in intricacy of the originals and the corrections. This can be a major hit to the accuracy of the measurement on *"how close the originals were to" being perfect* and defeat the purpose of *"grading by this closeness."*

A majority of the evaluator script is developed to detect tricks that allow deceptively succint corrections. They cannot be  handled by the script alone, which leads to the following problem:
- **Manual patching of deceptive corrections --** The evaluator script reports the corrections that are likely to be deceptive. They will have to be inspected and probably also patched manually by the evaluator person.


## How to use

The script has been specialized for our assessment structure, but those who would like to use it for their own may do so by adapting the following:
- **Programming language --** This one is for Python, but adaptations to other languages should be possible.
- **Folder structure --** We of course have our submission and grade report files at specific locations, and you should modify script to accommodate for your own folder structure.
- **Grade report file structure --** Same as above for the structure of our grade report file structure.
- **Submission preprocessing --** Our questions have a template uneditable code, and students must solve them by adding their code into regions marked off with some comment-flags. Script's preprocessor extracts those regions and measures similarity by those.

After those are covered, the rest is as usual and as follows:
1. Create a virtual environment (on Windows, execute `python -m venv env` on a terminal while inside the project directory)
1. Activate it (on Windows, `./env/Scripts/activate`)
1. Install requirements (`pip install -r requirements.txt`)
1. Run the script (`python main.py`)


## Thanks

I'd like to say "thank you" to the students of Cmpe150 - Fall 2022 who participated in our soft-objections cooperatively: I have received many valuable and supportive feedbacks from them, which has been the driving motivation of this project. 

I also thank the adversarial participants, i.e., the "calculating students": They have essentially acted as bug-reporters of the project, which allowed me to spot the shortcomings of the evaluator script. I hope that I was swift enough to catch up with their inconsideracy, though, so that the others didn't get negatively affected by an undeserved inflation of grades.
