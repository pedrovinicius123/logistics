import math
import numpy as np

import pygame

from graphics.planet_generator import (
    PLANET_SUN_DIRECTION,
    _sample_pixels_bilinear,
    asteroid_radius_factor,
    city_light_intensity,
    gas_giant_palette,
    generate_city_light_texture,
    generate_cloud_texture,
    generate_habitat_light_texture,
    generate_planet_texture,
    generate_starfield_surface,
)

from graphics.star import format_population

PLANET_TYPE_LABELS = {
    'terrestrial': 'Planeta terrestre',
    'gas_giant': 'Gigante gasoso',
    'asteroid': 'Asteroide do cinturao',
}

TRANSPORT_RESOURCES = ('Minerals', 'Food', 'Energy', 'Electronics',
                       'Chemicals', 'Alloys')


def planet_type_of(planet) -> str:
    return getattr(planet, 'planet_type', 'terrestrial')


class PlanetViewer3D:
    """Interactive software-rendered planet viewer embedded in the game UI."""

    def __init__(self, detail_level=3):
        self.yaw = 0.0
        self.pitch = 0.15
        self.zoom = 1.0
        self.detail_level = detail_level
        self._dragging = False
        self._texture_cache = {}
        self._layer_cache = {}
        self._pixel_layer_cache = {}
        self._sphere_geometry_cache = {}
        self._starfield_cache = {}
        self._sphere_rect = pygame.Rect(0, 0, 0, 0)
        self._close_rect = pygame.Rect(0, 0, 0, 0)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_ESCAPE, pygame.K_v):
            return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self._close_rect.collidepoint(event.pos):
                    return True
                self._dragging = self._sphere_rect.collidepoint(event.pos)
                return False
            if event.button == 4:
                self.zoom = min(1.6, self.zoom * 1.1)
                return False
            if event.button == 5:
                self.zoom = max(0.7, self.zoom / 1.1)
                return False

        if event.type == pygame.MOUSEWHEEL:
            self.zoom = min(1.6, max(0.7, self.zoom * 1.1 ** event.y))

        if event.type == pygame.MOUSEMOTION and self._dragging:
            self.yaw += event.rel[0] * 0.01
            self.pitch = min(1.2, max(-1.2, self.pitch + event.rel[1] * 0.01))

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging = False
        return False

    @staticmethod
    def _seed_for(planet):
        star = getattr(planet, 'parent_star', None)
        star_name = star.name if star is not None else ''
        return f"{star_name}:{planet.name}"

    def draw(self, screen, planet, title_font, body_font):
        width, height = screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((3, 8, 18, 210))
        screen.blit(overlay, (0, 0))

        card_width = min(760, width - 40)
        card_height = min(600, height - 40)
        card = pygame.Rect(
            (width - card_width) // 2, (height - card_height) // 2,
            card_width, card_height,
        )
        pygame.draw.rect(screen, (13, 23, 41), card, border_radius=12)
        starfield = self._starfield_cache.get(card.size)
        if starfield is None:
            starfield = generate_starfield_surface(card.size)
            self._starfield_cache[card.size] = starfield
        screen.blit(starfield, card.topleft)
        card_shade = pygame.Surface(card.size, pygame.SRCALPHA)
        card_shade.fill((5, 12, 24, 18))
        screen.blit(card_shade, card.topleft)
        pygame.draw.rect(screen, (61, 110, 142), card, 1, border_radius=12)

        title = title_font.render(planet.name, True, (224, 237, 247))
        screen.blit(title, (card.x + 24, card.y + 18))
        close_size = 30
        self._close_rect = pygame.Rect(
            card.right - close_size - 16, card.y + 14,
            close_size, close_size,
        )
        pygame.draw.rect(screen, (26, 48, 72), self._close_rect,
                         border_radius=5)
        pygame.draw.rect(screen, (61, 110, 142), self._close_rect, 1,
                         border_radius=5)
        close_label = body_font.render("X", True, (224, 237, 247))
        screen.blit(close_label, close_label.get_rect(
            center=self._close_rect.center))

        planet_type = planet_type_of(planet)
        sphere_radius = max(50, min(card.width // 3, card.height // 2 - 90))
        sphere_radius = round(sphere_radius * self.zoom)
        center = (card.centerx, card.centery - 6)
        self._sphere_rect = pygame.Rect(
            center[0] - sphere_radius, center[1] - sphere_radius,
            sphere_radius * 2, sphere_radius * 2,
        )
        pygame.draw.circle(screen, (26, 48, 72), center, sphere_radius + 7)
        pygame.draw.circle(screen, (82, 133, 166), center,
                           sphere_radius + 7, 1)

        rings = (planet_type == 'gas_giant'
                 and getattr(planet, 'has_rings', False))
        seed = self._seed_for(planet)
        if rings:
            self._draw_rings(screen, center, sphere_radius, seed, card,
                             front=False)

        habitats = int(getattr(planet, 'habitats', 0))
        capacity = planet.capacity_info()
        intensity = city_light_intensity(
            planet.developement, planet.population,
            capacity['max_dev'], capacity['max_pop'],
        )
        if planet_type != 'terrestrial':
            intensity = min(1.0, intensity * 0.85 + 0.06 * habitats)
        elif habitats:
            intensity = min(1.0, intensity + 0.03 * habitats)
        if not getattr(planet, 'is_colonized', False):
            intensity = 0.0
        sphere = self._render_sphere(planet, sphere_radius, intensity)
        screen.blit(sphere, (
            center[0] - sphere_radius, center[1] - sphere_radius))
        if planet_type == 'terrestrial':
            pygame.draw.circle(screen, (182, 219, 245), center,
                               sphere_radius, 1)
        if rings:
            self._draw_rings(screen, center, sphere_radius, seed, card,
                             front=True)
        if habitats:
            self._draw_habitat_stations(
                screen, center, sphere_radius, habitats)

        suitability = max(
            planet.life_suitability.values(), default=0.0)
        label = PLANET_TYPE_LABELS.get(planet_type, 'Planeta')
        if rings:
            label += ' com anéis'
        expansion_line = ''
        if getattr(planet, 'is_colonized', False):
            info = planet.expansion_info()
            remaining = (
                "mundo plenamente expandido" if info['percent'] >= 1.0
                and info['level'] >= info['max'] else
                f"próximo nível em ~{info['years_left']:.0f} anos")
            expansion_line = (
                f"Expansão {info['level']}/{info['max']}"
                f"  ·  {info['percent']:.0%}  ·  {remaining}"
                f"  ·  Habitats {habitats}")
        details = (
            f"{label}  ·  raio {planet.radius:.3f}",
            f"Desenvolvimento {planet.developement:.2f}"
            f"  |  População {format_population(planet.population)}",
        ) + ((expansion_line,) if expansion_line else ()) + (
            f"Simbiose máxima {suitability:.2f}"
            f"  |  Luzes urbanas {intensity:.0%}",
            "Arraste para girar  ·  roda para zoom  ·  Esc/V fecha",
        )
        line_y = card.bottom - 88 - (19 if expansion_line else 0)
        for index, text in enumerate(details):
            rendered = body_font.render(
                text, True, (137, 180, 203)
                if index == len(details) - 1 else (203, 222, 235),
            )
            screen.blit(rendered, (card.x + 24, line_y + index * 19))

        self._draw_logistics(screen, planet, body_font, card)

    def _draw_rings(self, screen, center, radius, seed, card, front):
        light, dark, _ = gas_giant_palette(seed)
        color = tuple(
            int(0.45 * dark[axis] + 0.55 * light[axis])
            for axis in range(3))
        cx, cy = center
        limit = min(card.centerx - card.x, card.width // 2) - 12
        semi_major = max(radius + 4, min(int(radius * 1.55), limit))
        semi_minor = max(3, int(semi_major * 0.28))
        dot = max(1, radius // 45)
        for index in range(200):
            t = index * math.tau / 200
            sin_t = math.sin(t)
            if (sin_t >= 0.0) != front:
                continue
            x = int(cx + semi_major * math.cos(t))
            y = int(cy + semi_minor * sin_t)
            pygame.draw.circle(screen, color, (x, y), dot)
            if dot > 1:
                pygame.draw.circle(screen, color, (x, y - 1), dot - 1)

    def _draw_habitat_stations(self, screen, center, radius, count):
        """Estações orbitais pálidas girando ao redor do mundo."""
        cx, cy = center
        orbit = radius * 1.28
        tilt = 0.35
        dot = max(2, radius // 48)
        phase = pygame.time.get_ticks() / 1000.0 * 0.25
        for index in range(min(count, 10)):
            angle = phase + math.tau * index / max(1, min(count, 10))
            x = cx + orbit * math.cos(angle)
            y = cy + orbit * tilt * math.sin(angle)
            depth = math.sin(angle)
            color = (178, 232, 255) if depth >= 0 else (96, 150, 190)
            pygame.draw.circle(screen, color, (int(x), int(y)), dot)
            pygame.draw.circle(screen, (40, 74, 100),
                               (int(x), int(y)), dot + 1, 1)

    def _draw_logistics(self, screen, planet, body_font, card):
        panel = pygame.Rect(
            card.right - 268, card.y + 60, 252, card.height - 150)
        background = pygame.Surface(panel.size, pygame.SRCALPHA)
        background.fill((8, 16, 30, 170))
        screen.blit(background, panel.topleft)
        pygame.draw.rect(screen, (61, 110, 142), panel, 1,
                         border_radius=6)
        y = panel.y + 10
        screen.blit(body_font.render(
            "LOGÍSTICA", True, (182, 219, 245)), (panel.x + 10, y))
        y += 20

        planet_type = planet_type_of(planet)
        notes = {
            'asteroid': (
                "Núcleo minerador:",
                "excedentes de minérios",
                "abastecem a rede de",
                "transportes da facção.",
            ),
            'gas_giant': (
                "Plataforma energética:",
                "superávits de energia",
                "abastecem a rede de",
                "transportes da facção.",
            ),
        }
        if planet_type in notes:
            color = ((203, 190, 150) if planet.is_colonized
                     else (150, 140, 110))
            for line in notes[planet_type]:
                screen.blit(body_font.render(
                    line, True, color), (panel.x + 10, y))
                y += 17

        if not planet.is_colonized or planet.faction is None:
            screen.blit(body_font.render(
                "Sem colônia — nenhuma rota ativa.",
                True, (137, 180, 203)), (panel.x + 10, y))
            return

        y += 4
        for resource in TRANSPORT_RESOURCES:
            stored = float(planet.planet_resources.get(resource, 0.0))
            capacity = float(planet.storage_capacity.get(resource, 0.0))
            ratio = stored / max(1.0, capacity)
            color = ((230, 130, 120) if ratio < 0.25 else
                     (235, 210, 120) if ratio < 0.55 else
                     (150, 210, 175))
            screen.blit(body_font.render(
                f"{resource:<12s}{stored:>7.0f} / {capacity:<7.0f}",
                True, color), (panel.x + 10, y))
            y += 17

        y += 4
        manager = getattr(planet.faction, 'logistics_manager', None)
        trips = (manager.trips_serving(planet)
                 if manager is not None else [])
        if not trips:
            screen.blit(body_font.render(
                "Nenhum transporte em rota.", True, (137, 180, 203)),
                (panel.x + 10, y))
            y += 18
        for ship in trips[:4]:
            if ship.mission_kind == 'population':
                cargo = f"{ship.population_cargo:.0f} migrantes"
            else:
                cargo = f"{ship.load:.0f} {ship.resource}"
            role = ("carregando" if ship.source is planet
                    else "descarregando")
            screen.blit(body_font.render(
                f"{ship.ship_id} · {role} {cargo}"[:42],
                True, (203, 222, 235)), (panel.x + 10, y))
            y += 17

    def _texture_for(self, planet):
        key = (id(planet), self.detail_level)
        texture = self._texture_cache.get(key)
        if texture is None:
            seed = self._seed_for(planet)
            texture = generate_planet_texture(
                planet.life_suitability, seed,
                detail_level=self.detail_level,
                planet_type=planet_type_of(planet))
            self._texture_cache[key] = texture
        return texture

    def _texture_layers_for(self, planet):
        key = (id(planet), self.detail_level)
        layers = self._layer_cache.get(key)
        if layers is None:
            texture = self._texture_for(planet)
            seed = self._seed_for(planet)
            planet_type = planet_type_of(planet)
            size = texture.get_size()
            if planet_type != 'terrestrial':
                layers = (
                    texture,
                    None,
                    generate_habitat_light_texture(
                        seed, size, self.detail_level,
                        style=planet_type),
                )
            else:
                layers = (
                    texture,
                    generate_cloud_texture(seed, size),
                    generate_city_light_texture(
                        planet.life_suitability, seed, size,
                        self.detail_level),
                )
            self._layer_cache[key] = layers
        return layers

    def _pixel_layers_for(self, planet):
        key = (id(planet), self.detail_level)
        pixel_layers = self._pixel_layer_cache.get(key)
        if pixel_layers is None:
            texture, clouds, cities = self._texture_layers_for(planet)
            pixel_layers = (
                np.transpose(
                    pygame.surfarray.array3d(texture), (1, 0, 2)
                ).astype(np.float32),
                None if clouds is None else np.transpose(
                    pygame.surfarray.array3d(clouds), (1, 0, 2)
                ).astype(np.float32),
                None if clouds is None else pygame.surfarray.array_alpha(
                    clouds).T.astype(np.float32),
                None if cities is None else np.transpose(
                    pygame.surfarray.array3d(cities), (1, 0, 2)
                ).astype(np.float32),
                None if cities is None else pygame.surfarray.array_alpha(
                    cities).T.astype(np.float32),
            )
            self._pixel_layer_cache[key] = pixel_layers
        return pixel_layers

    def _sphere_geometry_for(self, radius):
        geometry = self._sphere_geometry_cache.get(radius)
        if geometry is None:
            axis = (
                np.arange(radius * 2, dtype=np.float32) + 0.5 - radius
            ) / radius
            screen_x, screen_y = np.meshgrid(axis, -axis)
            z_squared = 1.0 - screen_x ** 2 - screen_y ** 2
            visible = z_squared >= 0.0
            screen_z = np.sqrt(np.maximum(0.0, z_squared))
            geometry = screen_x, screen_y, screen_z, visible
            self._sphere_geometry_cache[radius] = geometry
        return geometry

    def _render_sphere(self, planet, radius, city_intensity):
        pixel_layers = self._pixel_layers_for(planet)
        texture, cloud_pixels, cloud_alpha, city_pixels, city_alpha = (
            pixel_layers)
        planet_type = planet_type_of(planet)

        if planet_type == 'asteroid':
            seed = self._seed_for(planet)
            axis = (
                np.arange(radius * 2, dtype=np.float32) + 0.5 - radius
            ) / radius
            raw_x, raw_y = np.meshgrid(axis, -axis)
            theta = np.arctan2(raw_y, raw_x)
            factor = asteroid_radius_factor(seed, theta)
            screen_x = raw_x / factor
            screen_y = raw_y / factor
            z_squared = 1.0 - screen_x ** 2 - screen_y ** 2
            visible = z_squared >= 0.0
            screen_z = np.sqrt(np.maximum(0.0, z_squared))
        else:
            screen_x, screen_y, screen_z, visible = (
                self._sphere_geometry_for(radius))

        cos_pitch, sin_pitch = np.cos(self.pitch), np.sin(self.pitch)
        yaw_y = screen_y * cos_pitch + screen_z * sin_pitch
        yaw_z = -screen_y * sin_pitch + screen_z * cos_pitch
        cos_yaw, sin_yaw = np.cos(self.yaw), np.sin(self.yaw)
        world_x = screen_x * cos_yaw - yaw_z * sin_yaw
        world_y = yaw_y
        world_z = screen_x * sin_yaw + yaw_z * cos_yaw

        height, width = texture.shape[:2]
        longitude = np.arctan2(world_x, world_z)
        latitude = np.arcsin(np.clip(world_y, -1.0, 1.0))
        sample_x = (
            (longitude / (2.0 * np.pi) + 0.5) * width - 0.5)
        sample_y = (
            (0.5 - latitude / np.pi) * height - 0.5)

        sun = np.asarray(PLANET_SUN_DIRECTION, dtype=np.float32)
        sun /= np.linalg.norm(sun)
        illumination = (
            world_x * sun[0] + world_y * sun[1] + world_z * sun[2])
        transition = np.clip((illumination + 0.22) / 0.60, 0.0, 1.0)
        daylight = transition * transition * (3.0 - 2.0 * transition)
        ambient = {'terrestrial': 0.18, 'gas_giant': 0.15,
                   'asteroid': 0.06}.get(planet_type, 0.18)
        color = _sample_pixels_bilinear(
            texture, sample_x, sample_y) * (
                ambient + (1.0 - ambient) * daylight[..., None])

        # Aro de Fresnel: atm/espalho suave na borda do disco.
        fresnel = np.clip(1.0 - screen_z, 0.0, 1.0) ** 2.6 * visible
        rim = fresnel * (0.15 + 0.85 * daylight)
        rim_tint = {'terrestrial': (120.0, 170.0, 255.0),
                    'gas_giant': (150.0, 180.0, 225.0),
                    'asteroid': (120.0, 140.0, 170.0)}.get(
                        planet_type, (120.0, 170.0, 255.0))
        color += (np.asarray(rim_tint, dtype=np.float32)
                  * rim[..., None] * 0.45)

        if cloud_pixels is not None:
            clouds = _sample_pixels_bilinear(
                cloud_pixels, sample_x, sample_y)
            cloud_opacity = (
                _sample_pixels_bilinear(
                    cloud_alpha, sample_x, sample_y) / 255.0
                * (0.25 + 0.62 * daylight)
            )
            color = (
                color * (1.0 - cloud_opacity[..., None])
                + clouds * (0.3 + 0.7 * daylight[..., None])
                * cloud_opacity[..., None]
            )

        if city_pixels is not None and city_intensity > 0:
            lights = _sample_pixels_bilinear(
                city_pixels, sample_x, sample_y)
            city_opacity = (
                _sample_pixels_bilinear(
                    city_alpha, sample_x, sample_y) / 255.0
                * math.pow(min(1.0, max(0.0, city_intensity)), 0.35)
                * (1.0 - daylight) ** 1.15
            )
            city_opacity = np.clip(city_opacity * 1.9, 0.0, 1.0)
            color = (
                color * (1.0 - city_opacity[..., None])
                + lights * city_opacity[..., None] * 1.45
            )
        color = np.clip(color, 0, 255).astype(np.uint8)

        sphere = pygame.Surface(
            (radius * 2, radius * 2), pygame.SRCALPHA)
        rgb_pixels = pygame.surfarray.pixels3d(sphere)
        rgb_pixels[:, :, :] = np.transpose(color, (1, 0, 2))
        del rgb_pixels
        alpha_pixels = pygame.surfarray.pixels_alpha(sphere)
        alpha_pixels[:, :] = visible.T.astype(np.uint8) * 255
        del alpha_pixels
        return sphere

    def set_detail_level(self, detail_level):
        if detail_level != self.detail_level:
            self.detail_level = detail_level
            self._texture_cache.clear()
            self._layer_cache.clear()
            self._pixel_layer_cache.clear()
