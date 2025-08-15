import random

from .choices import ProfileColor


def get_random_color():
    return random.choice(ProfileColor.values)
