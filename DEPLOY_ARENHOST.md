# Arenhost backend

1. Create a Python App in cPanel.
2. Python: 3.9.23 or another available 3.9+ version.
3. Application root: `kalodata_app`.
4. Startup file: `passenger_wsgi.py`.
5. Entry point: `application`.
6. Upload `backend_api.py`, `kalodata_email_finder.py`, `passenger_wsgi.py`, `requirements.txt`.
7. Install dependencies: `pip install -r requirements.txt`.
8. Add environment variables:
   - `CHOCODATA_API_KEY`: your current Chocodata key.
   - `FRONTEND_ORIGIN`: `https://helmiandjustin.github.io`.
9. Set the frontend `API_BASE` in `frontend/index.html` to the backend URL.
10. Restart the Python app after changing files.

The GitHub Pages frontend never receives the Chocodata key.
