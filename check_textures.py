from types import SimpleNamespace

import numpy as np
import pygame

from graphics.planet_generator import (
    generate_city_light_texture,
    generate_cloud_texture,
    generate_planet_land_mask,
    generate_planet_surface,
    generate_planet_texture,
    generate_starfield_surface,
)
from graphics.ship_sprites import get_ship_sprite
from logistics.game_3d import PlanetViewer3D
from players.factions import DESIGNS
from players.ships import Warship


def check_textures():
    print(f"{'Suitability':<12} | {'Texture colors':<14} | "
          f"{'2D alpha coverage':<17} | {'Repeatable':<10}")
    print("-" * 65)
    all_valid = True
    for index, category in enumerate(('Human', 'Alien', 'Hybrid', 'Robot')):
        profile = {
            name: 0.9 if name == category else 0.2
            for name in ('Human', 'Alien', 'Hybrid', 'Robot')
        }
        seed = f"procedural-check-{index}"
        texture = generate_planet_texture(profile, seed)
        repeat = generate_planet_texture(profile, seed)
        land_mask = generate_planet_land_mask(
            seed, texture.get_size(), detail_level=3)
        surface = generate_planet_surface(
            profile, seed, size=96, city_lights=0.8)
        colors = np.unique(
            pygame.surfarray.array3d(texture).reshape(-1, 3), axis=0)
        alpha = pygame.surfarray.array_alpha(surface)
        coverage = np.count_nonzero(alpha) / alpha.size
        repeatable = (
            pygame.image.tobytes(texture, 'RGB')
            == pygame.image.tobytes(repeat, 'RGB')
        )
        land_coverage = np.count_nonzero(land_mask) / land_mask.size
        valid = (
            len(colors) > 100 and 0.45 < coverage < 0.8 and repeatable
            and 0.23 < land_coverage < 0.52
        )
        all_valid &= valid
        print(f"{category:<12} | {len(colors):<14} | "
              f"{coverage:>15.1%} | {str(repeatable):<10}")

    profile = {
        name: 0.9 if name == 'Human' else 0.2
        for name in ('Human', 'Alien', 'Hybrid', 'Robot')
    }
    low = generate_planet_texture(profile, 'detail-check', detail_level=1)
    low_repeat = generate_planet_texture(
        profile, 'detail-check', detail_level=1)
    high = generate_planet_texture(profile, 'detail-check', detail_level=8)
    detail_mask = generate_planet_land_mask(
        'detail-check', high.get_size(), detail_level=8)
    other_detail_mask = generate_planet_land_mask(
        'different-world', high.get_size(), detail_level=8)
    detail_valid = (
        pygame.image.tobytes(low, 'RGB')
        == pygame.image.tobytes(low_repeat, 'RGB')
        and pygame.image.tobytes(low, 'RGB')
        != pygame.image.tobytes(high, 'RGB')
        and high.get_width() > low.get_width()
        and high.get_height() > low.get_height()
        and not np.array_equal(detail_mask, other_detail_mask)
    )
    print(f"Texture pixels: {low.get_size()} -> {high.get_size()}")
    print(f"Texture detail levels 1-8: "
          f"{'OK' if detail_valid else 'FAILED'}")

    seam_mask = generate_planet_land_mask(
        'seam-check', (512, 256), detail_level=6)
    seam_repeat = generate_planet_land_mask(
        'seam-check', (512, 256), detail_level=6)
    seam_disagreement = np.mean(seam_mask[:, 0] != seam_mask[:, -1])
    seam_valid = (
        np.array_equal(seam_mask, seam_repeat)
        and seam_disagreement < 0.1
    )
    print(f"Procedural continents/longitude seam: "
          f"{'OK' if seam_valid else 'FAILED'} "
          f"({seam_disagreement:.1%} edge mismatch)")

    layer_size = high.get_size()
    clouds = generate_cloud_texture('layer-check', layer_size)
    clouds_repeat = generate_cloud_texture('layer-check', layer_size)
    cities_layer = generate_city_light_texture(
        profile, 'layer-check', layer_size, detail_level=8)
    city_alpha = pygame.surfarray.array_alpha(cities_layer)
    cloud_alpha = pygame.surfarray.array_alpha(clouds)
    city_land_mask = generate_planet_land_mask(
        'layer-check', layer_size, detail_level=8)
    starfield = generate_starfield_surface((320, 180))
    layers_valid = (
        clouds.get_size() == layer_size
        and cities_layer.get_size() == layer_size
        and np.count_nonzero(cloud_alpha) > 0
        and np.count_nonzero(city_alpha) > 0
        and not np.any(
            (city_alpha.T > 0) & ~city_land_mask)
        and pygame.image.tobytes(clouds, 'RGBA')
        == pygame.image.tobytes(clouds_repeat, 'RGBA')
        and starfield.get_size() == (320, 180)
    )
    print(f"Asset layers (terrain/clouds/cities/stars): "
          f"{'OK' if layers_valid else 'FAILED'}")

    unlit = generate_planet_surface(
        profile, 'city-check', size=128, detail_level=3)
    illuminated = generate_planet_surface(
        profile, 'city-check', size=128, city_lights=0.08, detail_level=3)
    opaque = pygame.surfarray.array_alpha(unlit) > 0
    changed = np.any(
        pygame.surfarray.array3d(unlit)
        != pygame.surfarray.array3d(illuminated),
        axis=2,
    )
    city_pixels = int(np.count_nonzero(changed & opaque))
    city_valid = city_pixels > 50
    print(f"City-light overlay: {city_pixels} changed pixels; "
          f"{'OK' if city_valid else 'FAILED'}")

    warship_designs = [
        design for design in DESIGNS.values()
        if design['class'] is Warship
    ]
    ship_designs_valid = (
        len(warship_designs) == 6
        and len({design['sprite'] for design in DESIGNS.values()}) == 9
    )
    all_ship_designs = (
        warship_designs
        + [DESIGNS[key] for key in ('scout', 'transport', 'colony')]
    )
    for design in all_ship_designs:
        sprite = get_ship_sprite(
            design['sprite'], (52, 164, 220), (32, 32))
        ship_designs_valid &= (
            sprite.get_size() == (32, 32)
            and np.count_nonzero(pygame.surfarray.array_alpha(sprite)) > 0
        )
    blue_sprite = get_ship_sprite(
        DESIGNS['corvette']['sprite'], (52, 152, 219), (32, 32))
    red_sprite = get_ship_sprite(
        DESIGNS['corvette']['sprite'], (231, 76, 60), (32, 32))
    ship_designs_valid &= (
        pygame.image.tobytes(blue_sprite, 'RGBA')
        != pygame.image.tobytes(red_sprite, 'RGBA')
    )
    print(f"Ship sprites: {len(warship_designs)} combat + "
          f"3 civilian roles; "
          f"{'OK' if ship_designs_valid else 'FAILED'}")

    pygame.font.init()
    viewer = PlanetViewer3D(detail_level=3)
    planet = SimpleNamespace(
        name='Viewer-check',
        parent_star=SimpleNamespace(name='Sol'),
        life_suitability=profile,
        developement=0.3,
        population=1000,
        capacity_info=lambda: {'max_dev': 1.0, 'max_pop': 1000.0},
    )
    screen = pygame.Surface((800, 600))
    viewer.draw(
        screen, planet, pygame.font.Font(None, 20),
        pygame.font.Font(None, 16))
    dim_sphere = pygame.surfarray.array3d(
        viewer._render_sphere(planet, 100, 0.08))
    visible_city_pixels = np.count_nonzero(
        (dim_sphere[:, :, 0] > dim_sphere[:, :, 1] * 1.05)
        & (dim_sphere[:, :, 0] > dim_sphere[:, :, 2] * 1.3)
    )
    original = pygame.image.tobytes(
        viewer._render_sphere(planet, 100, 0.08), 'RGBA')
    viewer.yaw = 0.7
    rotated = pygame.image.tobytes(
        viewer._render_sphere(planet, 100, 0.08), 'RGBA')
    viewer_valid = (
        bool(viewer._starfield_cache)
        and visible_city_pixels > 5
        and original != rotated
    )
    print(f"3D viewer layers/low-population city lights: "
          f"{'OK' if viewer_valid else 'FAILED'}")

    return (
        all_valid and detail_valid and seam_valid and layers_valid and city_valid
        and ship_designs_valid and viewer_valid
    )


if __name__ == '__main__':
    raise SystemExit(0 if check_textures() else 1)
