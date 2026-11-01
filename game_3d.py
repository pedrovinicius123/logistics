import math
import numpy as np

import pygame

from graphics.planet_generator import (
    PLANET_SUN_DIRECTION,
    _sample_pixels_bilinear,
    city_light_intensity,
    generate_city_light_texture,
    generate_cloud_texture,
    generate_planet_texture,
    generate_starfield_surface,
)


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

        sphere_radius = max(50, min(card.width // 3, card.height // 2 - 90))
        sphere_radius = round(sphere_radius * self.zoom)
        center = (card.centerx, card.centery + 12)
        self._sphere_rect = pygame.Rect(
            center[0] - sphere_radius, center[1] - sphere_radius,
            sphere_radius * 2, sphere_radius * 2,
        )
        pygame.draw.circle(screen, (26, 48, 72), center, sphere_radius + 7)
        pygame.draw.circle(screen, (82, 133, 166), center,
                           sphere_radius + 7, 1)

        capacity = planet.capacity_info()
        intensity = city_light_intensity(
            planet.developement, planet.population,
            capacity['max_dev'], capacity['max_pop'],
        )
        sphere = self._render_sphere(planet, sphere_radius, intensity)
        screen.blit(sphere, (
            center[0] - sphere_radius, center[1] - sphere_radius))
        pygame.draw.circle(screen, (182, 219, 245), center, sphere_radius, 1)

        suitability = max(
            planet.life_suitability.values(), default=0.0)
        details = (
            f"Desenvolvimento {planet.developement:.2f}"
            f"  |  População {planet.population:.0f}",
            f"Simbiose máxima {suitability:.2f}"
            f"  |  Luzes urbanas {intensity:.0%}",
            "Arraste para girar  ·  roda para zoom  ·  Esc/V fecha",
        )
        line_y = card.bottom - 72
        for index, text in enumerate(details):
            rendered = body_font.render(
                text, True, (137, 180, 203) if index == 2
                else (203, 222, 235),
            )
            screen.blit(rendered, (card.x + 24, line_y + index * 19))

    def _texture_for(self, planet):
        key = (id(planet), self.detail_level)
        texture = self._texture_cache.get(key)
        if texture is None:
            seed = f"{planet.parent_star.name}:{planet.name}"
            texture = generate_planet_texture(
                planet.life_suitability, seed,
                detail_level=self.detail_level)
            self._texture_cache[key] = texture
        return texture

    def _texture_layers_for(self, planet):
        key = (id(planet), self.detail_level)
        layers = self._layer_cache.get(key)
        if layers is None:
            texture = self._texture_for(planet)
            seed = f"{planet.parent_star.name}:{planet.name}"
            size = texture.get_size()
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
                np.transpose(
                    pygame.surfarray.array3d(clouds), (1, 0, 2)
                ).astype(np.float32),
                pygame.surfarray.array_alpha(clouds).T.astype(np.float32),
                np.transpose(
                    pygame.surfarray.array3d(cities), (1, 0, 2)
                ).astype(np.float32),
                pygame.surfarray.array_alpha(cities).T.astype(np.float32),
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
        texture, cloud_pixels, cloud_alpha, city_pixels, city_alpha = (
            self._pixel_layers_for(planet))
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
        daylight = np.clip(illumination, 0.0, 1.0)
        base = _sample_pixels_bilinear(
            texture, sample_x, sample_y) * (
                0.18 + 0.82 * daylight[..., None])

        clouds = _sample_pixels_bilinear(
            cloud_pixels, sample_x, sample_y)
        cloud_opacity = (
            _sample_pixels_bilinear(
                cloud_alpha, sample_x, sample_y) / 255.0
            * (0.25 + 0.62 * daylight)
        )
        color = (
            base * (1.0 - cloud_opacity[..., None])
            + clouds * (0.3 + 0.7 * daylight[..., None])
            * cloud_opacity[..., None]
        )

        lights = _sample_pixels_bilinear(
            city_pixels, sample_x, sample_y)
        city_opacity = (
            _sample_pixels_bilinear(
                city_alpha, sample_x, sample_y) / 255.0
            * math.pow(min(1.0, max(0.0, city_intensity)), 0.35)
            * np.clip(-illumination, 0.0, 1.0) ** 1.1
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
