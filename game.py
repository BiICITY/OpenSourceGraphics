"""Echo Cavern: a native 2D Pygame game using OpenSimplex cave fields.

Project game code generated with AI assistance. The imported
pygame and opensimplex packages are unmodified third-party open source.
"""
import argparse
import math
import random
import sys
from collections import deque
from dataclasses import dataclass

import pygame
from opensimplex import OpenSimplex


COLS, ROWS, TILE = 50, 32, 22
WIDTH, HEIGHT = COLS * TILE, ROWS * TILE
HUD = 92
FPS = 60
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
BG = (9, 14, 25)


@dataclass
class Enemy:
    x: int
    y: int
    alert: float = 0.0
    stun: float = 0.0
    investigate: object = None
    chasing: bool = False


@dataclass
class Shard:
    x: int
    y: int
    got: bool = False
    ping: float = 0.0


class Game:
    def __init__(self, seed=None):
        pygame.init()
        pygame.display.set_caption("Echo Cavern | 에코 동굴")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT + HUD))
        self.clock = pygame.time.Clock()
        self.font = self.pick_font(18)
        self.small = self.pick_font(15)
        self.large = self.pick_font(37, bold=True)
        self.keys = set()
        self.level = 0
        self.fixed_seed = seed
        self.new_cave(seed)

    @staticmethod
    def pick_font(size, bold=False):
        for name in ("malgungothic", "nanumgothic", "arialunicode", "arial"):
            if name in pygame.font.get_fonts():
                return pygame.font.SysFont(name, size, bold=bold)
        return pygame.font.Font(None, size + 4)

    def say(self, message):
        self.message = message

    def floor(self, x, y):
        return 0 < x < COLS - 1 and 0 < y < ROWS - 1 and self.tiles[y][x] != 0

    def carve(self, x, y):
        if 0 < x < COLS - 1 and 0 < y < ROWS - 1:
            self.tiles[y][x] = 1

    def distances(self, source):
        result = {source: 0}
        queue = deque([source])
        while queue:
            x, y = queue.popleft()
            for dx, dy in DIRS:
                p = (x + dx, y + dy)
                if self.floor(*p) and p not in result:
                    result[p] = result[(x, y)] + 1
                    queue.append(p)
        return result

    def choose_far(self, distance, minimum, avoid=(), dead_end=False):
        cells = []
        for (x, y), d in distance.items():
            if d < minimum or x < 2 or y < 2 or x > COLS - 3 or y > ROWS - 3:
                continue
            if any(abs(x - ax) + abs(y - ay) < 10 for ax, ay in avoid):
                continue
            if dead_end and sum(self.floor(x + dx, y + dy) for dx, dy in DIRS) != 1:
                continue
            cells.append((d, x, y))
        if not cells and dead_end:
            return self.choose_far(distance, minimum, avoid, False)
        if not cells:
            return None
        cells.sort(reverse=True)
        _, x, y = self.rng.choice(cells[:min(38, len(cells))])
        return x, y

    def new_cave(self, seed=None):
        self.level += 1
        self.seed = int(seed if seed is not None else random.randrange(1, 2**31))
        self.rng = random.Random(self.seed)
        self.noise = OpenSimplex(seed=self.seed)
        self.tiles = [[0 for _ in range(COLS)] for _ in range(ROWS)]
        self.field = [[self.noise.noise2(x * .115, y * .115) for x in range(COLS)] for y in range(ROWS)]
        self.player = [3, 15]

        # Growing-tree maze: every carved branch connects to the start.
        stack = [tuple(self.player)]
        self.carve(*stack[0])
        while stack:
            x, y = stack[-1]
            options = []
            for dx, dy in DIRS:
                nx, ny = x + 2 * dx, y + 2 * dy
                if 1 < nx < COLS - 2 and 1 < ny < ROWS - 2 and not self.floor(nx, ny):
                    options.append((nx, ny, x + dx, y + dy))
            if options:
                nx, ny, mx, my = self.rng.choice(options)
                self.carve(mx, my)
                self.carve(nx, ny)
                stack.append((nx, ny))
            else:
                stack.pop()

        # OpenSimplex is a coherent 2D scalar field. High values create pockets;
        # low values leave thicker rock. All openings touch an existing corridor.
        for y in range(2, ROWS - 2):
            for x in range(2, COLS - 2):
                near = sum(self.floor(x + dx, y + dy) for dx, dy in DIRS)
                if not self.floor(x, y) and near >= 2 and (self.field[y][x] > .26 or self.rng.random() < .045):
                    self.carve(x, y)
        for _ in range(7):
            x, y = self.rng.randrange(4, COLS - 4), self.rng.randrange(4, ROWS - 4)
            if self.floor(x, y) and self.field[y][x] > -.12:
                for yy in range(y - 1, y + 2):
                    for xx in range(x - 1, x + 2):
                        self.carve(xx, yy)

        distance = self.distances(tuple(self.player))
        self.exit = self.choose_far(distance, 35, [tuple(self.player)]) or max(distance, key=distance.get)
        positions = []
        for k in range(3):
            pos = self.choose_far(distance, 15 + k * 4, [tuple(self.player), self.exit] + positions, True)
            if pos is None:
                pos = self.choose_far(distance, 5, [tuple(self.player), self.exit] + positions)
            if pos is not None:
                positions.append(pos)
        self.shards = [Shard(*p) for p in positions]
        # Farthest-point placement spreads enemies across the whole cave.
        # Keep them away from the spawn, exit, and shards at the start.
        landmarks = [tuple(self.player), self.exit] + positions
        candidates = [p for p, d in distance.items()
                      if d >= 18 and 2 <= p[0] < COLS - 2 and 2 <= p[1] < ROWS - 2
                      and all(math.hypot(p[0] - q[0], p[1] - q[1]) >= 7 for q in landmarks)]
        enemy_positions = []
        for _ in range(9):
            if not candidates:
                break
            anchors = enemy_positions or [tuple(self.player)]
            best = max(candidates, key=lambda p: (
                min(math.hypot(p[0] - q[0], p[1] - q[1]) for q in anchors),
                self.rng.random()))
            enemy_positions.append(best)
            candidates.remove(best)
        self.enemies = [Enemy(*p) for p in enemy_positions]

        self.seen = [[False for _ in range(COLS)] for _ in range(ROWS)]
        self.flash = [[0.0 for _ in range(COLS)] for _ in range(ROWS)]
        self.hearts = 3
        self.collected = 0
        self.charges = 3
        self.used = 0
        self.cooldown = 0.0
        self.ring = 0.0
        self.echo_dir = None
        self.invulnerable = 0.0
        self.move_timer = 0.0
        self.enemy_timer = 0.0
        self.steps = 0
        self.state = "ready"
        self.keys.clear()
        self.reveal(3.5, 0)
        self.say("WASD 이동 | Space 넓은 음파 | 이동키 + Space 방향 음파 | 총 3회")

    def reveal(self, radius, duration):
        px, py = self.player
        for y in range(max(0, int(py - radius)), min(ROWS, int(py + radius + 1))):
            for x in range(max(0, int(px - radius)), min(COLS, int(px + radius + 1))):
                if math.hypot(x - px, y - py) <= radius:
                    self.seen[y][x] = True
                    self.flash[y][x] = max(self.flash[y][x], duration)

    def held_direction(self):
        for codes, direction in (((pygame.K_w, pygame.K_UP), (0, -1)),
                                 ((pygame.K_s, pygame.K_DOWN), (0, 1)),
                                 ((pygame.K_a, pygame.K_LEFT), (-1, 0)),
                                 ((pygame.K_d, pygame.K_RIGHT), (1, 0))):
            if any(key in self.keys for key in codes):
                return direction
        return None

    def echo(self):
        if self.state != "playing" or self.cooldown > 0:
            return
        if self.charges == 0:
            self.say("음파 3회를 모두 사용했어요. 열린 길로 탈출하세요.")
            return
        direction = self.held_direction()
        focused = direction is not None
        self.charges -= 1
        self.used += 1
        self.cooldown = 1.7 if focused else 2.4
        self.ring = .55
        self.echo_dir = direction
        px, py = self.player

        def inside(x, y, radius):
            dx, dy = x - px, y - py
            distance = math.hypot(dx, dy)
            return distance <= radius and (not focused or distance < 1.5 or
                   (dx * direction[0] + dy * direction[1]) / distance > .70)

        for y in range(ROWS):
            for x in range(COLS):
                if inside(x, y, 13 if focused else 11):
                    self.seen[y][x] = True
                    self.flash[y][x] = max(self.flash[y][x], 1.9 if focused else 2.6)
        broken = 0
        for y in range(max(1, py - 6), min(ROWS - 1, py + 7)):
            for x in range(max(1, px - 6), min(COLS - 1, px + 7)):
                if self.tiles[y][x] == 0 and inside(x, y, 5.5 if focused else 2.6):
                    # Fragile rocks (higher noise value) respond more often.
                    chance = max(.47, min(.96, .77 + .30 * self.field[y][x]))
                    if self.rng.random() < chance:
                        self.tiles[y][x] = 2
                        broken += 1
        pings = 0
        for shard in self.shards:
            if not shard.got and inside(shard.x, shard.y, 17 if focused else 12):
                shard.ping = 2.3
                pings += 1
        stunned = 0
        for enemy in self.enemies:
            distance = math.hypot(enemy.x - px, enemy.y - py)
            if distance < (12 if focused else 24):
                enemy.alert = 2.5 if focused else 4.2
                enemy.investigate = (px, py)
            if distance <= 3.5:
                enemy.stun = 1.0
                stunned += 1
        self.say(("방향" if focused else "넓은") +
                 " 음파: 벽 {}칸 붕괴 | 조각 울림 {}개 | 적 {}명 기절".format(broken, pings, stunned))

    def move(self, dx, dy):
        if self.state != "playing":
            return
        x, y = self.player[0] + dx, self.player[1] + dy
        if not self.floor(x, y):
            return
        self.player[:] = [x, y]
        self.steps += 1
        self.reveal(3.5, 0)
        for shard in self.shards:
            if not shard.got and (shard.x, shard.y) == (x, y):
                shard.got = True
                self.collected += 1
                self.say("빛 조각 발견! {}/3".format(self.collected))
        if (x, y) == self.exit:
            if self.collected == 3:
                self.state = "won"
                self.say("탈출 성공! {}걸음, 음파 {}회 사용".format(self.steps, self.used))
            else:
                self.say("출구 발견. 조각 3개를 모으면 열립니다.")
        self.hit_check()

    def hit_check(self):
        if self.state != "playing" or self.invulnerable > 0:
            return
        for enemy in self.enemies:
            if enemy.stun <= 0 and (enemy.x, enemy.y) == tuple(self.player):
                self.hearts -= 1
                self.invulnerable = 1.7
                self.say("추적자에게 닿았어요!" if self.hearts else "탐험 실패. R로 새 동굴을 만드세요.")
                if not self.hearts:
                    self.state = "lost"
                break

    def move_enemies(self):
        distance_cache = {}
        for enemy in self.enemies:
            # Detection uses direct Euclidean distance, including through walls.
            # It is recalculated on every enemy step, so crossing 6 tiles ends pursuit.
            enemy.chasing = math.hypot(enemy.x - self.player[0], enemy.y - self.player[1]) <= 6
            if enemy.stun > 0:
                continue
            options = [(enemy.x + dx, enemy.y + dy) for dx, dy in DIRS
                       if self.floor(enemy.x + dx, enemy.y + dy)]
            if not options:
                continue
            if enemy.chasing:
                destination = tuple(self.player)
            elif enemy.alert > 0 and enemy.investigate != (enemy.x, enemy.y):
                # Sound is investigated at its old position; the moving player
                # is not tracked beyond the six-tile detection radius.
                destination = enemy.investigate
            else:
                destination = None
                enemy.alert = 0
                enemy.investigate = None
            if destination is not None:
                if destination not in distance_cache:
                    distance_cache[destination] = self.distances(destination)
                distance = distance_cache[destination]
                shortest = min(distance.get(p, 10**9) for p in options)
                target = self.rng.choice([p for p in options if distance.get(p, 10**9) == shortest])
            else:
                target = self.rng.choice(options)
            enemy.x, enemy.y = target
            enemy.chasing = math.hypot(enemy.x - self.player[0], enemy.y - self.player[1]) <= 6
        self.hit_check()

    def update(self, dt):
        if self.state != "playing":
            return
        self.cooldown = max(0, self.cooldown - dt)
        self.ring = max(0, self.ring - dt)
        self.invulnerable = max(0, self.invulnerable - dt)
        for enemy in self.enemies:
            enemy.alert = max(0, enemy.alert - dt)
            enemy.stun = max(0, enemy.stun - dt)
            enemy.chasing = math.hypot(enemy.x - self.player[0], enemy.y - self.player[1]) <= 6
        for shard in self.shards:
            shard.ping = max(0, shard.ping - dt)
        for row in self.flash:
            for x in range(COLS):
                row[x] = max(0, row[x] - dt)
        self.move_timer += dt
        self.enemy_timer += dt
        if self.move_timer >= .105:
            direction = self.held_direction()
            if direction:
                self.move(*direction)
                self.move_timer = 0
        if self.enemy_timer >= .36:
            self.move_enemies()
            self.enemy_timer = 0

    @staticmethod
    def text(surface, font, value, pos, color=(225, 239, 255)):
        surface.blit(font.render(value, True, color), pos)

    def visible(self, x, y):
        return self.seen[y][x] and (self.flash[y][x] > 0 or
               math.hypot(x - self.player[0], y - self.player[1]) < 4)

    def draw(self):
        s = self.screen
        s.fill(BG)
        pygame.draw.rect(s, (15, 25, 41), (0, 0, WIDTH, HEIGHT))
        px, py = self.player
        for y in range(ROWS):
            for x in range(COLS):
                if not self.seen[y][x]:
                    continue
                value = self.field[y][x]
                lit = self.flash[y][x] > 0 or math.hypot(x - px, y - py) < 3.5
                if self.tiles[y][x] == 0:
                    base = (70 + int(value * 18), 80 + int(value * 15), 104 + int(value * 12))
                elif self.tiles[y][x] == 2:
                    base = (65, 106, 113)
                else:
                    base = (30 + int(value * 10), 56 + int(value * 10), 73 + int(value * 13))
                if not lit:
                    base = tuple(max(5, int(v * .35)) for v in base)
                rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                pygame.draw.rect(s, base, rect)
                if self.tiles[y][x] == 0 and lit:
                    pygame.draw.line(s, (112, 131, 151), (rect.x + 2, rect.y + 3),
                                     (rect.right - 3, rect.y + 3), 1)
                if self.tiles[y][x] == 2:
                    pygame.draw.circle(s, (109, 194, 185), rect.center, 2)
        for shard in self.shards:
            if not shard.got and self.visible(shard.x, shard.y):
                cx, cy = shard.x * TILE + TILE // 2, shard.y * TILE + TILE // 2
                pygame.draw.polygon(s, (119, 235, 255), [(cx, cy - 9), (cx + 8, cy),
                                                         (cx, cy + 9), (cx - 8, cy)])
        if self.visible(*self.exit):
            x, y = self.exit
            pygame.draw.rect(s, (135, 249, 179) if self.collected == 3 else (72, 129, 110),
                             (x * TILE + 4, y * TILE + 2, 14, 18), border_radius=3)
            pygame.draw.rect(s, (17, 52, 42), (x * TILE + 7, y * TILE + 6, 7, 14))
        for enemy in self.enemies:
            if self.visible(enemy.x, enemy.y):
                color = ((151, 230, 255) if enemy.stun > 0 else
                         (255, 98, 114) if enemy.chasing else
                         (255, 177, 95) if enemy.alert > 0 else (174, 119, 177))
                center = (enemy.x * TILE + 11, enemy.y * TILE + 11)
                pygame.draw.circle(s, color, center, 9)
                pygame.draw.circle(s, (25, 26, 39), (center[0] - 3, center[1] - 1), 1)
                pygame.draw.circle(s, (25, 26, 39), (center[0] + 3, center[1] - 1), 1)
                if enemy.stun > 0:
                    pygame.draw.circle(s, (218, 249, 255), center, 12, 2)
        if self.invulnerable <= 0 or int(self.invulnerable * 8) % 2 == 0:
            pygame.draw.circle(s, (255, 226, 166), (px * TILE + 11, py * TILE + 11), 9)
            pygame.draw.circle(s, (255, 250, 218), (px * TILE + 8, py * TILE + 8), 2)
        if self.ring > 0:
            radius = int((1 - self.ring / .55) * (280 if self.echo_dir else 240))
            center = (px * TILE + 11, py * TILE + 11)
            if self.echo_dir:
                angle = math.atan2(self.echo_dir[1], self.echo_dir[0])
                points = [center] + [(center[0] + int(radius * math.cos(angle + a)),
                                      center[1] + int(radius * math.sin(angle + a)))
                                     for a in (-.77, -.38, 0, .38, .77)]
                pygame.draw.lines(s, (130, 218, 255), False, points, 3)
            elif radius > 0:
                pygame.draw.circle(s, (130, 218, 255), center, radius, 3)
        for shard in self.shards:
            if not shard.got and shard.ping > 0:
                angle = math.atan2(shard.y - py, shard.x - px)
                cx = px * TILE + 11 + math.cos(angle) * 52
                cy = py * TILE + 11 + math.sin(angle) * 52
                points = [(cx + 13 * math.cos(angle), cy + 13 * math.sin(angle)),
                          (cx + 7 * math.cos(angle + 2.45), cy + 7 * math.sin(angle + 2.45)),
                          (cx + 7 * math.cos(angle - 2.45), cy + 7 * math.sin(angle - 2.45))]
                pygame.draw.polygon(s, (126, 242, 255), points)

        pygame.draw.rect(s, (15, 27, 44), (0, HEIGHT, WIDTH, HUD))
        pygame.draw.line(s, (69, 103, 132), (0, HEIGHT), (WIDTH, HEIGHT), 2)
        self.text(s, self.font, "HP " + "♥" * self.hearts, (20, HEIGHT + 11), (255, 195, 198))
        self.text(s, self.font, "SHARDS {}/3".format(self.collected), (170, HEIGHT + 11), (132, 231, 248))
        self.text(s, self.font, "ECHO {}/3".format(self.charges), (350, HEIGHT + 11), (255, 223, 152))
        self.text(s, self.font, "CAVE #{}  SEED {}".format(self.level, self.seed), (510, HEIGHT + 11), (167, 190, 210))
        self.text(s, self.small, self.message, (20, HEIGHT + 46), (215, 231, 248))
        self.text(s, self.small, "WASD/Arrows move | Space echo | Direction + Space focused | Red: chase <=6 | Orange: sound | R: new cave", (20, HEIGHT + 68), (141, 170, 194))
        if self.state in ("ready", "won", "lost"):
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((5, 13, 27, 160))
            s.blit(overlay, (0, 0))
            title = {"ready": "ENTER THE ECHO CAVERN", "won": "ESCAPED!", "lost": "CAUGHT IN THE CAVE"}[self.state]
            self.text(s, self.large, title, (WIDTH // 2 - self.large.size(title)[0] // 2, HEIGHT // 2 - 42),
                      (181, 243, 255) if self.state == "ready" else (157, 255, 192) if self.state == "won" else (255, 175, 180))
            hint = "Press WASD, arrow key, or Space" if self.state == "ready" else "Press R for a new cave"
            self.text(s, self.font, hint, (WIDTH // 2 - self.font.size(hint)[0] // 2, HEIGHT // 2 + 15))
        pygame.display.flip()

    def run(self):
        while True:
            dt = min(.05, self.clock.tick(FPS) / 1000)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        return
                    if event.key == pygame.K_r:
                        self.new_cave()
                        continue
                    if self.state == "ready" and event.key in (pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d,
                           pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_SPACE):
                        self.state = "playing"
                        self.say("빛 조각 3개를 모아 출구를 찾으세요.")
                    if event.key == pygame.K_SPACE:
                        self.echo()
                    else:
                        self.keys.add(event.key)
                if event.type == pygame.KEYUP:
                    self.keys.discard(event.key)
                if event.type == pygame.WINDOWFOCUSLOST:
                    self.keys.clear()
            self.update(dt)
            self.draw()


def main():
    parser = argparse.ArgumentParser(description="Echo Cavern native 2D game")
    parser.add_argument("--seed", type=int, help="Reproduce a specific generated cave")
    parser.add_argument("--check", action="store_true", help="Generate and validate one cave without opening a window")
    args = parser.parse_args()
    if args.check:
        import os
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    game = Game(args.seed)
    if args.check:
        distance = game.distances(tuple(game.player))
        assert game.exit in distance
        assert len(game.shards) == 3 and all((s.x, s.y) in distance for s in game.shards)
        assert len(game.enemies) == 9
        print("OK seed={} reachable={} shards={} enemies={}".format(game.seed, len(distance), len(game.shards), len(game.enemies)))
        pygame.quit()
    else:
        game.run()


if __name__ == "__main__":
    main()
