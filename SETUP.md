# Setup: from zip to running needles

## 1. Create the GitHub repo (private)
1. Sign in at github.com. Click the + (top right) > New repository.
2. Name it `election-needle`. Choose **Private**. Do not add a README. Click Create repository.
3. Unzip election_needle.zip on your computer.
4. Upload the files. Easiest, no tools needed: on the new repo's page click "uploading an existing file",
   drag in EVERYTHING inside the unzipped folder (including the hidden `.github` folder and `.gitignore`;
   if your computer hides dot-folders, turn on "show hidden files"), and click Commit changes.
   Check that `.github/workflows/update.yml` shows up in the repo. If it did not, use
   Add file > Create new file, type `.github/workflows/update.yml` as the name, and paste the file's text.
5. Never upload raw Georgia county voter files (they contain voter names and addresses).

## 2. Let the workflow save results
Repo > Settings > Actions > General > scroll to "Workflow permissions" > choose
**Read and write permissions** > Save.

## 3. Test run
Repo > Actions tab > "update-needle" > Run workflow > Run workflow. Wait about a minute.
- A green check means it ran. Open the new commit "needle update": it should add `data/latest.json`.
- A red X: open the run, click the failed step, and send me the last 20 lines of its log.
- The VoteHub step may fail or print "0 parsed" the first time; that does not stop the run. Send me the
  step's log and the file `data/votehub_unparsed.txt` if it exists.

## 4. Put the app online (Streamlit Community Cloud)
1. Go to share.streamlit.io and sign in with GitHub.
2. New app > pick the `election-needle` repo, branch `main`, main file `app.py` > Deploy.
3. In the app's sidebar choose Data: "Latest published (GitHub)". Georgia should show both needles.
   For a private repo, Streamlit reads the file from the repo it is deployed from, so leave the URL blank.

## 5. Daily routine until election day
- **Georgia early vote:** copy the two dashboard tables into absentee.txt and inperson.txt, run
  `python ga_paste.py absentee.txt inperson.txt`, and upload the two new `early.csv` files
  (data/GA/governor/early.csv and data/GA/u-s-senate/early.csv).
- **Polls:** send me the poll tables, or edit `data/poll_inputs_2026.csv`.
- **New state:** send me its county history (2016-2024 general elections), polls, and any early-vote
  data. I build the baseline and add it to config/races.json.

## 6. After election week
Actions tab > update-needle > ... menu > Disable workflow.

## Schedule (UTC, Actions can start a few minutes late)
Every 12 hours; every 10 minutes from 6pm ET Nov 3 to about 9am ET Nov 4. Times are in
`.github/workflows/update.yml`.
