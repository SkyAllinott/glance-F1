from fastapi import FastAPI

from API_Endpoints.current_race_cleaner import router as current_race_cleaner
from API_Endpoints.constructors_cleaner import router as constructors_cleaner
from API_Endpoints.drivers_cleaner import router as drivers_cleaner
from API_Endpoints.map.router import router as map_router
from API_Endpoints.pit_championship.router import router as pitstop_router

app = FastAPI()

# Include all routers
app.include_router(current_race_cleaner, prefix="/f1/next_race")
app.include_router(constructors_cleaner, prefix="/f1/constructors_standings")
app.include_router(drivers_cleaner, prefix="/f1/drivers_standings")
app.include_router(map_router, prefix="/f1/next_map")
app.include_router(pitstop_router, prefix = "/f1/pitstop_standings")
