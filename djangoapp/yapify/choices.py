from django.db import models


class ProfileColor(models.TextChoices):
    RED = "RED", "Red"
    BLUE = "BLUE", "Blue"
    GREEN = "GREEN", "Green"
    YELLOW = "YELLOW", "Yellow"
    ORANGE = "ORANGE", "Orange"
    PURPLE = "PURPLE", "Purple"
    PINK = "PINK", "Pink"
    BROWN = "BROWN", "Brown"
    BLACK = "BLACK", "Black"
    WHITE = "WHITE", "White"
    GREY = "GREY", "Grey"
    CYAN = "CYAN", "Cyan"
    MAGENTA = "MAGENTA", "Magenta"


class QuoteVisibility(models.TextChoices):
    MUTUALS = "mutuals", "Mutual Friends Only"
    EXTENDED = "extended", "Friends of Friends"


class QuoteResponse(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed"
    DENIED = "denied", "Denied"
