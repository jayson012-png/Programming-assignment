
from database import Database
from gui import App
from services import Services


if __name__ == "__main__":
    App(Services(Database())).mainloop()
