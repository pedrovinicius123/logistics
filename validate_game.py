try:
    import pygame
    from OpenGL.GL import *
    from OpenGL.GLU import *
    import game_3d
    print('Imports successful')
    game = game_3d.Game3D()
    print('Game initialized successfully without texture errors.')
except Exception as e:
    print(f'Validation failed: {e}')
    exit(1)