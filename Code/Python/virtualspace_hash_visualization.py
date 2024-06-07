import numpy as np
import hashlib
import sys
import random, secrets
from panda3d.core import Point3, AmbientLight, DirectionalLight, LVecBase4f, TextNode
from panda3d.core import Geom, GeomNode, GeomVertexData, GeomVertexFormat, GeomVertexWriter, GeomTriangles
from panda3d.core import NodePath
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.gui.OnscreenText import OnscreenText

# Configurable parameters
CUBE_SIZE = 0.01
SPACING = 0.04
CAMERA_SPEED = 0.5
TURN_SPEED = 100
PITCH_SPEED = 50
MATRIX_HEIGHT = 2
ENABLE_VISUAL_EFFECTS = True  # Option to enable visual effects

# Function to generate a 32-byte hash from a string and convert it to a binary matrix
def hash_to_binary_matrix(seed_string):
    hash_bytes = hashlib.sha256(seed_string.encode('utf-8')).digest()[:24]  # Get 24 bytes from the hash
    binary_matrix = np.unpackbits(np.frombuffer(hash_bytes, dtype=np.uint8)).reshape((8, 8, 3))
    return binary_matrix

class MyApp(ShowBase):
    def __init__(self, seed_string):
        ShowBase.__init__(self)
        self.disableMouse()

        # Generate binary matrix from the hash
        binary_matrix = hash_to_binary_matrix(seed_string)

        # Add ground
        self.ground = self.create_plane(size=50)
        self.ground.reparentTo(self.render)
        self.ground.setPos(0, 0, 0)
        self.ground.setColor(0.5, 0.5, 0.5, 1)  # Gray color

        # Add cubes based on the binary matrix
        self.cubes = []
        self.cube_nodes = []  # Store nodes for visual effects
        for x in range(binary_matrix.shape[0]):
            for y in range(binary_matrix.shape[1]):
                for z in range(binary_matrix.shape[2]):
                    if binary_matrix[x, y, z] == 1:
                        cube = self.create_cube(size=CUBE_SIZE)
                        cube.reparentTo(self.render)
                        cube.setPos(Point3(x * SPACING, y * SPACING, z * SPACING + MATRIX_HEIGHT))  # Offset Z to float above ground
                        initial_color = (random.uniform(0, 0.2), random.uniform(0.5, 1), random.uniform(0, 0.2), 1)
                        cube.setColor(*initial_color)  # Shades of green
                        self.cubes.append(cube)
                        self.cube_nodes.append((cube, initial_color))

        # Setup lights
        ambientLight = AmbientLight("ambientLight")
        ambientLight.setColor((0.5, 0.5, 0.5, 1))
        ambientLightNP = self.render.attachNewNode(ambientLight)
        self.render.setLight(ambientLightNP)

        directionalLight = DirectionalLight("directionalLight")
        directionalLight.setDirection(Point3(-5, -5, -5))
        directionalLight.setColor((0.7, 0.7, 0.7, 1))
        directionalLightNP = self.render.attachNewNode(directionalLight)
        self.render.setLight(directionalLightNP)

        # Camera settings
        self.camera.setPos(0, -2, MATRIX_HEIGHT)  # Set camera at the same height as the cubes
        self.heading = 0
        self.pitch = 0
        self.speed = CAMERA_SPEED
        self.turn_speed = TURN_SPEED
        self.pitch_speed = PITCH_SPEED

        # Movement controls
        self.keyMap = {
            "forward": False, "backward": False, "left": False, "right": False,
            "turn_left": False, "turn_right": False, "look_up": False, "look_down": False
        }

        self.accept("w", self.updateKeyMap, ["forward", True])
        self.accept("w-up", self.updateKeyMap, ["forward", False])
        self.accept("s", self.updateKeyMap, ["backward", True])
        self.accept("s-up", self.updateKeyMap, ["backward", False])
        self.accept("a", self.updateKeyMap, ["left", True])
        self.accept("a-up", self.updateKeyMap, ["left", False])
        self.accept("d", self.updateKeyMap, ["right", True])
        self.accept("d-up", self.updateKeyMap, ["right", False])
        self.accept("q", self.updateKeyMap, ["turn_left", True])
        self.accept("q-up", self.updateKeyMap, ["turn_left", False])
        self.accept("e", self.updateKeyMap, ["turn_right", True])
        self.accept("e-up", self.updateKeyMap, ["turn_right", False])
        self.accept("arrow_up", self.updateKeyMap, ["look_up", True])
        self.accept("arrow_up-up", self.updateKeyMap, ["look_up", False])
        self.accept("arrow_down", self.updateKeyMap, ["look_down", True])
        self.accept("arrow_down-up", self.updateKeyMap, ["look_down", False])

        self.taskMgr.add(self.update, "update")

        # Add onscreen text to display information about the matrix
        self.info_text = OnscreenText(
            text=f"Seed: {seed_string}\nCubes: {np.sum(binary_matrix)}\nSize: {CUBE_SIZE}\nSpacing: {SPACING}",
            pos=(-1.3, 0.9), scale=0.07, fg=(1, 1, 1, 1), align=TextNode.ALeft
        )

        # Add visual effects if enabled
        if ENABLE_VISUAL_EFFECTS:
            self.taskMgr.add(self.visual_effects, "visual_effects")

    def updateKeyMap(self, key, state):
        self.keyMap[key] = state

    def update(self, task):
        dt = globalClock.getDt()

        # Movement logic
        if self.keyMap["forward"]:
            self.camera.setPos(self.camera, Point3(0, self.speed * dt, 0))
        if self.keyMap["backward"]:
            self.camera.setPos(self.camera, Point3(0, -self.speed * dt, 0))
        if self.keyMap["left"]:
            self.camera.setPos(self.camera, Point3(-self.speed * dt, 0, 0))
        if self.keyMap["right"]:
            self.camera.setPos(self.camera, Point3(self.speed * dt, 0, 0))
        if self.keyMap["turn_left"]:
            self.heading += self.turn_speed * dt
            self.camera.setH(self.heading)
        if self.keyMap["turn_right"]:
            self.heading -= self.turn_speed * dt
            self.camera.setH(self.heading)
        if self.keyMap["look_up"]:
            self.pitch += self.pitch_speed * dt
            self.camera.setP(self.pitch)
        if self.keyMap["look_down"]:
            self.pitch -= self.pitch_speed * dt
            self.camera.setP(self.pitch)

        return Task.cont

    def visual_effects(self, task):
        time = globalClock.getFrameTime() * 2  # Adjust time scaling for smoother effects
        for node, initial_color in self.cube_nodes:
            scale = 1.0 + 0.1 * np.sin(time)
            node.setScale(scale)

            # Pulsing color effect
            r = initial_color[0] + 0.1 * np.sin(time)
            g = initial_color[1] + 0.1 * np.sin(time + 2)
            b = initial_color[2] + 0.1 * np.sin(time + 4)
            node.setColor(r, g, b, 1)

        return Task.cont

    def create_plane(self, size):
        format = GeomVertexFormat.getV3()
        vdata = GeomVertexData("plane", format, Geom.UHStatic)

        vertex = GeomVertexWriter(vdata, "vertex")

        vertex.addData3(-size, -size, 0)
        vertex.addData3(size, -size, 0)
        vertex.addData3(size, size, 0)
        vertex.addData3(-size, size, 0)

        prim = GeomTriangles(Geom.UHStatic)
        prim.addVertices(0, 1, 2)
        prim.addVertices(2, 3, 0)

        geom = Geom(vdata)
        geom.addPrimitive(prim)

        node = GeomNode("plane")
        node.addGeom(geom)

        return NodePath(node)

    def create_cube(self, size):
        format = GeomVertexFormat.getV3()
        vdata = GeomVertexData("cube", format, Geom.UHStatic)

        vertex = GeomVertexWriter(vdata, "vertex")

        # Define vertices for a cube
        vertices = [
            (-size, -size, -size), (size, -size, -size),
            (size, size, -size), (-size, size, -size),
            (-size, -size, size), (size, -size, size),
            (size, size, size), (-size, size, size)
        ]

        for v in vertices:
            vertex.addData3(v)

        prim = GeomTriangles(Geom.UHStatic)
        prim.addVertices(0, 1, 2)
        prim.addVertices(2, 3, 0)
        prim.addVertices(4, 5, 6)
        prim.addVertices(6, 7, 4)
        prim.addVertices(0, 1, 5)
        prim.addVertices(5, 4, 0)
        prim.addVertices(2, 3, 7)
        prim.addVertices(7, 6, 2)
        prim.addVertices(1, 2, 6)
        prim.addVertices(6, 5, 1)
        prim.addVertices(3, 0, 4)
        prim.addVertices(4, 7, 3)

        geom = Geom(vdata)
        geom.addPrimitive(prim)

        node = GeomNode("cube")
        node.addGeom(geom)

        return NodePath(node)

if __name__ == "__main__":
    seed_string = sys.argv[1] if len(sys.argv) > 1 else secrets.token_urlsafe(32)
    app = MyApp(seed_string)
    app.run()
