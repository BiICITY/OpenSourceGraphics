"""Three small reproducible OSS demos used before integrating the game.

Run: python oss_examples.py
Results are written to examples/ as PNG files.
"""
from pathlib import Path

import pygame
from opensimplex import OpenSimplex


OUT = Path(__file__).resolve().parent / "examples"
OUT.mkdir(exist_ok=True)
pygame.init()

# 1. Pygame's basic 2D primitives and pixel coordinate system.
surface = pygame.Surface((520, 300))
surface.fill((15, 25, 43))
pygame.draw.rect(surface, (71, 104, 141), (40, 35, 125, 125))
pygame.draw.circle(surface, (255, 216, 151), (275, 95), 54)
pygame.draw.polygon(surface, (117, 226, 244), ((415, 36), (482, 153), (343, 153)))
pygame.draw.line(surface, (211, 240, 255), (50, 225), (470, 225), 4)
pygame.image.save(surface, str(OUT / "01_pygame_primitives.png"))

# 2. OpenSimplex coherent 2D values: nearby coordinates have similar values.
noise = OpenSimplex(seed=42)
surface = pygame.Surface((520, 300))
for y in range(300):
    for x in range(520):
        n = noise.noise2(x * .018, y * .018)
        value = max(0, min(255, int(128 + 120 * n)))
        surface.set_at((x, y), (value, value, value))
pygame.image.save(surface, str(OUT / "02_opensimplex_field.png"))

# 3. Change one threshold: the same field becomes an island-like binary mask.
surface = pygame.Surface((520, 300))
for y in range(300):
    for x in range(520):
        n = noise.noise2(x * .018, y * .018)
        surface.set_at((x, y), (37, 79, 97) if n > .12 else (71, 81, 105))
pygame.image.save(surface, str(OUT / "03_noise_threshold.png"))
pygame.quit()
print("Wrote three examples to", OUT)
