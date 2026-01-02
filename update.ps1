echo "Updating project..."
.\venv\Scripts\Activate.ps1
git stash save
git pull
echo "Update complete."