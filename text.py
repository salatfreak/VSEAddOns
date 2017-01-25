# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNUGeneral Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# Add-on meta data
bl_info = {
    "name": "Add Rendered Text Effect",
    "author": "Salatfreak",
    "version": (0, 1),
    "blender": (2, 75),
    "location": "Video Sequence Editor > Add > Effect Strip > Rendered Text",
    "description": "Adds text effect",
    "warning": "",
    "wiki_url": "",
    "category": "Sequencer"
}

# Constants
MAX_CHANNEL = 32
DEFAULT_DIR = "//renders/text"

# Import modules
import bpy
import re
from os import path

### Object Properties ###
#########################

# Location
def get_location(self):
    text_object = list(filter(
        lambda o: o.type == 'FONT', self.scene.objects
    ))[0]
    return text_object.location.xy
def set_location(self, location):
    text_object = list(filter(
        lambda o: o.type == 'FONT', self.scene.objects
    ))[0]
    text_object.location.xy = location
text_location = bpy.props.FloatVectorProperty(
    size=2, name="Location", get=get_location, set=set_location
)

# Scale
def get_scale(self):
    text_object = list(filter(
        lambda o: o.type == 'FONT', self.scene.objects
    ))[0]
    return text_object.scale.x
def set_scale(self, scale):
    text_object = list(filter(
        lambda o: o.type == 'FONT', self.scene.objects
    ))[0]
    if text_object.scale.x == 0:
        text_object.scale.yz = (scale, scale)
    else:
        text_object.scale.y = text_object.scale.y / text_object.scale.x * scale
        text_object.scale.z = text_object.scale.z / text_object.scale.x * scale
    text_object.scale.x = scale
text_scale = bpy.props.FloatProperty(name="Scale", get=get_scale, set=set_scale)

### Effect operator ###
########################

# Add text scene operator
class TextSceneAddOperator(bpy.types.Operator):
    # Meta data
    bl_idname="sf_addons.text_scene_effect_add"
    bl_label="Add Text Scene Effect"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties
    text = bpy.props.StringProperty(name="Text", default="Title")

    # Show only in sequence editor
    @classmethod
    def poll(cls, context):
        return (context.space_data.type == 'SEQUENCE_EDITOR')

    # Prepare data
    def invoke(self, context, event):
        # Set start and end frame
        self.text_strip_start = context.scene.frame_current
        self.text_strip_duration = 5 * context.scene.render.fps

        # Show property dialog
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    # Layout property
    def draw(self, context):
        self.layout.prop(self, 'text')

    # Add rendered text
    def execute(self, context):
        # Store Sequencer Scene
        sequencer_scene = context.scene

        # Add new scene
        text_scene = bpy.data.scenes.new(
            "Text_"+ re.sub(
                r'[^A-Za-z0-9_]', "", re.sub(r'\s', "", self.text)
            )[:16]
        )

        # Copy render settings
        text_scene.render.resolution_x = context.scene.render.resolution_x
        text_scene.render.resolution_y = context.scene.render.resolution_y
        text_scene.render.resolution_percentage = 100
        text_scene.render.fps = context.scene.render.fps

        # Output settings
        text_scene.render.use_overwrite = True
        text_scene.render.use_file_extension = False
        text_scene.render.image_settings.file_format = 'PNG'
        text_scene.render.filepath = path.join(
            DEFAULT_DIR, text_scene.name[5:] +".png"
        )

        # Set edit screen for scene tools addon
        if hasattr(text_scene, 'sf_scene_props'):
            # Find first screen containing default
            screen_found = False
            for screen in bpy.data.screens:
                if "default" in screen.name.lower():
                    text_scene.sf_scene_props.edit_screen = screen.name
                    screen_found = True
                    break

            # Find first screen containing 3d else
            if not screen_found:
                for screen in bpy.data.screens:
                    if "3d" in screen.name.lower():
                        text_scene.sf_scene_props.edit_screen = screen.name
                        break

        # Set up text scene
        context.screen.scene = text_scene
        text_scene.frame_start = text_scene.frame_end = 1
        text_scene.render.alpha_mode = 'TRANSPARENT'
        text_scene.world = bpy.data.worlds.new("Text")
        text_scene.world.horizon_color = [0, 0, 0]

        # Add camera
        bpy.ops.object.camera_add()
        text_scene.camera = text_scene.objects.active
        text_scene.camera.location.z = text_scene.camera.data.lens / 16

        # Add text
        bpy.ops.object.text_add()
        text_object = text_scene.objects.active
        text_object.data.offset_y = -0.35
        text_object.data.align_x = 'CENTER'
        text_object.data.body = self.text

        # Set up material
        bpy.ops.object.material_slot_add()
        text_material = bpy.data.materials.new("Text")
        text_material.diffuse_color.r = 1
        text_material.diffuse_color.g = 1
        text_material.diffuse_color.b = 1
        text_material.use_shadeless = True
        text_object.material_slots[0].material = text_material

        # Position text
        text_object.scale.xyz = 0.3

        # Switch back to sequencer scene
        context.screen.scene = sequencer_scene

        # Add text scene strip
        bpy.ops.sequencer.scene_strip_add(
            scene=text_scene.name,
            frame_start=self.text_strip_start,
            replace_sel=True
        )

        # Get strip
        text_strip = context.scene.sequence_editor.active_strip

        # Set up strip
        text_strip.name = text_scene.name
        text_strip.frame_final_duration = self.text_strip_duration

        return {'FINISHED'}

# Text scene button
def text_scene_button(self, context):
    self.layout.operator(
        TextSceneAddOperator.bl_idname,
        text="Text Scene",
        icon='PLUGIN'
    )

### Rendered text strip panel ###
#################################

# Text strip panel
class TextStripPanel(bpy.types.Panel):
    # Meta data
    bl_label = "Text Strip"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"

    # Show only for text strips
    @classmethod
    def poll(self, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (
            strip is not None \
            and strip.type == 'SCENE' \
            and strip.scene is not None \
            and sum(o.type == 'FONT' for o in strip.scene.objects) > 0
        )

    # Draw panel
    def draw(self, context):
        strip = context.scene.sequence_editor.active_strip

        text_objects = list(filter(
            lambda o: o.type == 'FONT', strip.scene.objects
        ))

        # Text
        text_object = text_objects[0]
        self.layout.prop(text_object.data, "body", text="")

        # Positioning
        self.layout.prop(strip, "sf_text_location", text="Loc")
        self.layout.prop(strip, "sf_text_scale")

        # Material
        if len(text_object.material_slots) == 1 and \
            text_object.material_slots[0].material is not None:
            material = text_object.material_slots[0].material

            # Color row
            color_row = self.layout.row()
            color_row.prop(material, "diffuse_color", text="")
            if strip.scene.world is not None:
                color_row.prop(strip.scene.render, "alpha_mode", text="")
                color_row.prop(strip.scene.world, "horizon_color", text="")

### Module registration ###
###########################AA

# Register module
def register():
    # Register module
    bpy.utils.register_module(__name__)

    # Register strip properties
    bpy.types.SceneSequence.sf_text_location = text_location
    bpy.types.SceneSequence.sf_text_scale = text_scale

    # Add button
    bpy.types.SEQUENCER_MT_add_effect.append(text_scene_button)

# Unregister module
def unregister():
    # Unregister module
    bpy.utils.unregister_module(__name__)

    # Unregister strip properties
    del bpy.types.SceneSequence.sf_text_location
    del bpy.types.SceneSequence.sf_text_scale

    # Remove button
    bpy.types.SEQUENCER_MT_add_effect.remove(text_scene_button)

# Register if executed as script
if __name__ == '__main__':
    register()
