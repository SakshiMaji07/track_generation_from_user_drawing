import pygame
import json

def run():
    pygame.init()
    screen = pygame.display.set_mode((400, 200))
    pygame.display.set_caption("Live Race Stats")

    font = pygame.font.SysFont("Arial", 24)
    clock = pygame.time.Clock()

    # ✅ INITIAL LOAD
    try:
        with open("live_data.json", "r") as f:
            data = json.load(f)
    except:
        data = {"time": 0.0, "cones": 0}

    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # ✅ CONTINUOUS READ
        try:
            with open("live_data.json", "r") as f:
                data = json.load(f)
        except:
            data = {"time": 0.0, "cones": 0}

        screen.fill((20, 20, 20))

        time_text = font.render(f"Time: {data['time']:.2f}s", True, (255,255,255))
        cones_text = font.render(f"Cones: {data['cones']}", True, (255,255,255))

        screen.blit(time_text, (50, 50))
        screen.blit(cones_text, (50, 100))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()

if __name__ == "__main__":
    run()