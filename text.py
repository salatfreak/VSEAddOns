# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
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
DEFAULT_DIR = "//assets/titles/"

# Import modules
import bpy
import os
import uuid

### Helper functions ###
########################

# Get scene from ID
def get_scene(scene_id):
    # Find and return scene with matching ID
    for scene in bpy.data.scenes:
        if scene.text_props.id == scene_id:
            return scene

    # Return None if no scene matches
    return None

# Switch screen
def switch_screen(context, screen_name):
    for i in range(len(bpy.data.screens)):
        # Break if found
        if context.screen.name == screen_name: break

        # Switch to next screen
        bpy.ops.screen.screen_set(delta=1)

### Object properties ###
#########################

# Text scene property group
class SceneTextProps(bpy.types.PropertyGroup):
    # Is text scene property
    is_text_scene = bpy.props.BoolProperty(name="Is text Scene", default=False)

    # Parent scene ID
    parent_scene_id = bpy.props.StringProperty(name="Parent Scene ID")

    # Get scenes
    def get_screens(self, context):
        return [(scr.name, scr.name, "") for scr in bpy.data.screens]

    # Parent screen
    parent_screen = bpy.props.EnumProperty(
        name="Parent Screen", items=get_screens
    )

    # ID property
    id = bpy.props.StringProperty(name="Unique ID", default="")

    # Text edit screen
    edit_screen = bpy.props.EnumProperty(name="Edit screen", items=get_screens)

# Text strip property group
class ImageStripTextProps(bpy.types.PropertyGroup):
    # Is text strip property
    is_text_strip = bpy.props.BoolProperty(name="Is text Strip", default=False)

    # Scene ID
    scene_id = bpy.props.StringProperty(name="Scene ID", default="")

### Effect operator ###
########################

# Add rendered text operator
class RenderedTextAddOperator(bpy.types.Operator):
    # Meta data
    bl_idname="vse_text.rendered_text_effect_add"
    bl_label="Add Rendered Text Effect"
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

        # Add image strip
        bpy.ops.sequencer.image_strip_add(
            directory=DEFAULT_DIR,
            frame_start=self.text_strip_start,
            replace_sel=True,
            use_placeholders=True
        )
        
        # Get strip
        text_strip = context.scene.sequence_editor.active_strip

        # Set up strip
        text_strip.name = "Text_"+ self.text.replace(" ", "_")\
            .replace("\t", "_")[:16]
        text_strip.frame_final_duration = self.text_strip_duration
        text_strip.text_props.is_text_strip = True

        # Add new scene
        text_scene = bpy.data.scenes.new(text_strip.name)
        text_scene.text_props.is_text_scene = True
        text_scene.text_props.id = uuid.uuid4().hex

        # Link parent scene
        if context.scene.text_props.id == "":
            context.scene.text_props.id = uuid.uuid4().hex
        text_scene.text_props.parent_scene_id = context.scene.text_props.id

        # Link text scene
        text_strip.text_props.scene_id = text_scene.text_props.id

        # Copy render settings
        text_scene.render.resolution_x = context.scene.render.resolution_x
        text_scene.render.resolution_y = context.scene.render.resolution_y
        text_scene.render.resolution_percentage = 100
        text_scene.render.fps = context.scene.render.fps

        # Output settings
        text_scene.render.use_overwrite = True
        text_scene.render.use_file_extension = False
        text_scene.render.image_settings.file_format = 'PNG'
        text_scene.render.filepath = DEFAULT_DIR + text_scene.name[5:] +".png"

        # Find first screen containing default
        screen_found = False
        for screen in bpy.data.screens:
            if "default" in screen.name.lower():
                text_scene.text_props.edit_screen = screen.name
                screen_found = True
                break

        # Find first screen containing 3d else
        if not screen_found:
            for screen in bpy.data.screens:
                if "3d" in screen.name.lower():
                    text_scene.text_props.edit_screen = screen.name
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
        text_object.data.align = 'CENTER'
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

        return {'FINISHED'}

# Rendered text button
def rendered_text_button(self, context):
    self.layout.operator(
        RenderedTextAddOperator.bl_idname,
        text="Rendered Text",
        icon='PLUGIN'
    )

### Rendered text strip panel ###
#################################

# Render text operator
class RenderTextOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "vse_text.render_text"
    bl_label = "Render Text"
    bl_description = "Render Text Scene"

    # Show only for text strips
    @classmethod
    def poll(cls, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (strip is not None and strip.type == 'IMAGE' and \
            strip.text_props.is_text_strip and \
            get_scene(strip.text_props.scene_id) is not None)

    # Render text
    def invoke(self, context, event):
        strip = context.scene.sequence_editor.active_strip
        scene = get_scene(strip.text_props.scene_id)

        # Render text
        bpy.ops.render.render(write_still=True, scene=scene.name)

        # Update image
        while len(strip.elements) > 1:
            strip.elements.pop(0)
        strip.elements.append(os.path.split(scene.render.filepath)[-1])
        strip.elements.pop(0)
        
        return {'FINISHED'}

# Switch to text editing operator
class SwitchToTextEditingOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "vse_text.switch_to_text_editing"
    bl_label = "Switch to Text Editing"
    bl_description = "Switch to text scene editing"

    # Show only for text strips
    @classmethod
    def poll(self, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (strip is not None and strip.type == 'IMAGE' and \
            strip.text_props.is_text_strip and \
            get_scene(strip.text_props.scene_id) is not None)

    # Switch scene
    def invoke(self, context, event):
        strip = context.scene.sequence_editor.active_strip
        text_scene = get_scene(strip.text_props.scene_id)

        # Set scene properties
        text_scene.text_props.parent_screen = context.screen.name

        # Get text editing screen
        switch_screen(context, text_scene.text_props.edit_screen)

        # Switch to scene
        context.screen.scene = text_scene

        return {'FINISHED'}

# Remove text strip operator
class RemoveTextStripOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "vse_text.remove_text_strip"
    bl_label = "Remove text strip"
    bl_description = "Remove text scene and sequencer strip"

    # Show only for text Strips
    @classmethod
    def poll(cls, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (strip is not None and strip.type == 'IMAGE' and \
            strip.text_props.is_text_strip and \
            get_scene(strip.text_props.scene_id) is not None)

    # Show confirmation dialog
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    # Remove scene and strip
    def execute(self, context):
        strip = context.scene.sequence_editor.active_strip
        scene = get_scene(strip.text_props.scene_id)

        # Remove scene
        bpy.data.scenes.remove(scene)

        # Remove strip (taking groups into account)
        selected = context.selected_sequences
        for seq in selected:
            seq.select = False
        strip.select = True
        bpy.ops.sequencer.delete()
        for seq in selected:
            seq.select = True

        return {'FINISHED'}

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
        return (strip is not None and strip.type =='IMAGE' and \
            strip.text_props.is_text_strip and \
            get_scene(strip.text_props.scene_id) is not None)

    # Draw panel
    def draw(self, context):
        strip = context.scene.sequence_editor.active_strip
        scene = get_scene(strip.text_props.scene_id)

        text_objects = list(filter(
            lambda o: o.type == 'FONT', scene.objects
        ))

        # Text
        if len(text_objects) == 1:
            text_object = text_objects[0]
            self.layout.prop(text_object.data, "body", text="")
            
            # Color align row
            color_align_row = self.layout.row()
            if len(text_object.material_slots) == 1 and \
                text_object.material_slots[0].material is not None:
                material = text_object.material_slots[0].material
            
            # Color row
            color_row = self.layout.row()
            color_row.prop(material, "diffuse_color", text="")
            if scene.world is not None:
                color_row.prop(scene.render, "alpha_mode", text="")
                color_row.prop(scene.world, "horizon_color", text="")

        # Rendering
        self.layout.prop(scene.render, "filepath", text="")
        self.layout.operator(
            RenderTextOperator.bl_idname, text="Render", icon='RENDER_STILL'
        )
        
        # Edit
        self.layout.separator()
        self.layout.operator(
            SwitchToTextEditingOperator.bl_idname, text="Edit Text",
            icon='TEXT'
        )
        self.layout.prop(
            scene.text_props, 'edit_screen', text="", icon='SPLITSCREEN'
        )
        
        # Removal
        self.layout.operator(
            RemoveTextStripOperator.bl_idname, text="Remove", icon='X'
        )

### Text scene panel ###
#############################

# Switch to sequence editor operator
class SwitchToSequenceEditorOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "vse_text.switch_to_sequence_editor"
    bl_label = "Back to Sequencer"
    bl_description = "Switch back to the Sequence Editor"

    # Show only for text scenes
    @classmethod
    def poll(self, context):
        return context.scene.text_props.is_text_scene

    # Switch scene
    def invoke(self, context, event):
        # Get text properties
        text_props = context.scene.text_props

        # Switch screen
        switch_screen(context, text_props.parent_screen)

        # Switch to scene
        scene = get_scene(text_props.parent_scene_id)
        if scene is not None:
            context.screen.scene = scene
        else:
            self.report({'ERROR'}, "Sequence editing scene missing")

        return {'FINISHED'}

# Switch to sequence editor Panel
class TextScenePanel(bpy.types.Panel):
    # Meta data
    bl_label = "Text Strip"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    # Show only for text scenes
    @classmethod
    def poll(self, context):
        return context.scene.text_props.is_text_scene

    # Draw panel
    def draw(self, context):
        self.layout.operator(
            SwitchToSequenceEditorOperator.bl_idname, icon='SEQ_SEQUENCER'
        )

### Module registration ###
###########################AA

# Register module
def register():
    # Register module
    bpy.utils.register_module(__name__)

    # Register image strip properties
    bpy.types.ImageSequence.text_props = bpy.props.PointerProperty(
        type=ImageStripTextProps
    )

    # Register scene properties
    bpy.types.Scene.text_props = bpy.props.PointerProperty(
        type=SceneTextProps
    )

    # Add button
    bpy.types.SEQUENCER_MT_add_effect.append(rendered_text_button)

# Unregister module
def unregister():
    # Unregister module
    bpy.utils.unregister_module(__name__)

    # Unregister text properties
    del bpy.types.ImageSequence.text_props

    # Unregister scene properties
    del bpy.types.Scene.text_props

    # Remove button
    bpy.types.SEQUENCER_MT_add_effect.remove(rendered_text_button)

# Register if executed as script
if __name__ == '__main__':
    register()
