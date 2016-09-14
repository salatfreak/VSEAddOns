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
    "name": "Add Transform 3D Effect",
    "author": "Salatfreak",
    "version": (0, 1),
    "blender": (2, 75),
    "location": "Video Sequence Editor > Add > Effect Strip > Transform 3D",
    "description": "Adds transform 3D effect",
    "warning": "",
    "wiki_url": "",
    "category": "Sequencer"
}

# Constants
MAX_CHANNEL = 32

# Import modules
import bpy
import os
import re
import uuid
from functools import reduce
from mathutils import Vector

### Helper functions ###
########################

# Get scene from ID
def get_scene(scene_id):
    # Find and return scene with matching ID
    for scene in bpy.data.scenes:
        if scene.transform_props.id == scene_id:
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

# Get containing sequence list
def get_sequence_list(scene, strip):
    sequenceLists = [scene.sequence_editor.sequences]

    # Search depth first for sequence list
    while len(sequenceLists) != 0:
        seqList = sequenceLists.pop()
        for seq in seqList:
            if seq == strip:
                return seqList
            elif seq.type == 'META':
                sequenceLists.append(seq.sequences)

### RegExp preparation ###
##########################

img_ext_pattern = reduce(
    lambda p, ext: p +"|"+ ext[1:], bpy.path.extensions_image, ""
)[1:]
img_seq_re = re.compile("^(.*[^\d])?(\d+)\.("+ img_ext_pattern +")$")

### Object properties ###
#########################

# Transform scene property group
class SceneTransform3DProps(bpy.types.PropertyGroup):
    # Is transform scene property
    is_transform_scene = bpy.props.BoolProperty(name="Is transform 3D Scene", default=False)

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

    # Transform edit screen
    edit_screen = bpy.props.EnumProperty(name="Edit screen", items=get_screens)

### Effect operator ###
########################

# Add transform effect operator
class Transform3DEffectAddOperator(bpy.types.Operator):
    # Meta data
    bl_idname="vse_transform3d.transform_3d_effect_add"
    bl_label="Add Transform 3D Effect"
    bl_options = {'REGISTER', 'UNDO'}

    # Show only in sequence editor
    @classmethod
    def poll(cls, context):
        return (context.space_data.type == 'SEQUENCE_EDITOR')

    # Prepare data
    def invoke(self, context, event):
        # Get source strips
        self.source_strips = self.get_source_strips(context)

        # Require at least one strip
        if len(self.source_strips) == 0:
            self.report(
                {'ERROR'}, "At least one selected sequence strip is needed"
            )
            return {'CANCELLED'}

        # Require all strips to be images or movies
        for seq in self.source_strips:
            if seq.type not in {'MOVIE', 'IMAGE'}:
                self.report({'ERROR'}, "Only Image and Movie strips allowed")
                return {'CANCELLED'}

        # Find strip start and end frame
        self.transform_strip_start = max(
            [strip.frame_final_start for strip in self.source_strips]
        )
        self.transform_strip_end = min(
            [strip.frame_final_end for strip in self.source_strips]
        )

        # Require shared frames
        if self.transform_strip_start >= self.transform_strip_end:
            self.report({'ERROR'}, "Strips must have shared frames")
            return {'CANCELLED'}

        # Get following channel
        highest_channel = max(
            [strip.channel for strip in self.source_strips]
        )
        self.transform_strip_channel = (highest_channel + 1) % (MAX_CHANNEL + 1)

        # Get sequences per channel
        sequences = get_sequence_list(context.scene, self.source_strips[0])
        channel_seqs = [[] for i in range(MAX_CHANNEL + 1)]
        for seq in sequences:
            channel_seqs[seq.channel].append(seq)

        # Find first fitting channel
        channel_found = False
        while self.transform_strip_channel != highest_channel:
            # Count up on conflict
            if any(not(seq.frame_final_end < self.transform_strip_start or \
                self.transform_strip_end < seq.frame_final_start)
                    for seq in channel_seqs[self.transform_strip_channel]):
                self.transform_strip_channel = \
                    (self.transform_strip_channel % MAX_CHANNEL) + 1
            # Stop search else
            else:
                channel_found = True
                break

        # Require fitting channel
        if not channel_found:
            self.report({'ERROR'}, "Fitting channel required")
            return {'CANCELLED'}

        # Call execute
        return self.execute(context)

    # Add rendered text
    def execute(self, context):
        se = context.scene.sequence_editor
        seq_scene = context.scene

        # Create image plane
        def create_plane(strip, multi):
            # Add image plane
            bpy.ops.mesh.primitive_plane_add()
            image_plane = context.scene.objects.active
            image_plane.name = "Plane"+ strip.name

            # Scale image plane
            res = Vector((
                context.scene.render.resolution_x,
                context.scene.render.resolution_y
            ))
            if res.x >= res.y:
                image_plane.scale.y = res.y / res.x
            else:
                image_plane.scale.x = res.x / res.y
            bpy.ops.object.transform_apply(scale=True)

            # Set up material
            bpy.ops.object.material_slot_add()
            plane_material = bpy.data.materials.new(
                "Transform3D"+ strip.name
            )
            plane_material.use_shadeless = True
            plane_material.use_transparency = True
            plane_material.alpha = 0
            image_plane.material_slots[0].material = plane_material
            plane_material.texture_slots.add()

            # Unwrap plane
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.uv.unwrap()
            bpy.ops.object.mode_set(mode='OBJECT')
            layer = image_plane.data.uv_layers[0]
            layer.data[2].uv[1] = layer.data[2].uv[0]
            layer.data[3].uv[1] = layer.data[2].uv[1]

            # Set up texture slot
            plane_material.texture_slots[0].uv_layer = layer.name
            plane_material.texture_slots[0].use_map_alpha = True

            # Setup texture
            plane_texture = bpy.data.textures.new(plane_material.name, 'IMAGE')

            # Get file path
            if strip.type == 'MOVIE':
                image_source = 'MOVIE'
                image_path = strip.filepath
            else:
                image_source = 'SEQUENCE' if len(strip.elements) > 1 else 'FILE'
                image_path = os.path.join(
                    strip.directory, strip.elements[0].filename
                )

            # Find image
            image = None
            for img in bpy.data.images:
                if img.filepath == image_path and img.source == image_source:
                    image = img
                    break

            # Load image if not found
            if image is None:
                try:
                    image = bpy.data.images.load(image_path)
                    image.source = image_source
                except: pass

            # Assign image
            plane_texture.image = image

            # Assign texture
            plane_material.texture_slots[0].texture = plane_texture

            # Set up image
            img_offset = 0
            if strip.type == 'MOVIE':
                # Auto refresh frames
                plane_texture.image_user.use_auto_refresh = True
            elif len(strip.elements) > 1:
                # Match iamge file
                match = img_seq_re.match(strip.elements[0].filename)

                # Set offset
                img_offset = int(
                    match.string[match.regs[2][0]:match.regs[2][1]]
                ) -1

                # Auto refresh frames
                plane_texture.image_user.use_auto_refresh = True

            # Set up frames
            user = plane_texture.image_user
            if multi:
                user.frame_offset = self.transform_strip_start \
                    - strip.frame_start + strip.animation_offset_start \
                    + img_offset
                user.frame_duration = self.transform_strip_end \
                    - self.transform_strip_start
            else:
                user.frame_start = strip.animation_offset_start + 1
                user.frame_offset = strip.animation_offset_start + img_offset
                user.frame_duration = strip.frame_duration

            # Return image plane
            return image_plane

        # Assign scene id
        if seq_scene.transform_props.id == "":
            seq_scene.transform_props.id = uuid.uuid4().hex

        # Add new scene
        transform_scene = bpy.data.scenes.new(
            "Transform3D_"+ self.source_strips[-1].name
        )
        transform_scene.transform_props.is_transform_scene = True
        transform_scene.transform_props.parent_scene_id = \
            seq_scene.transform_props.id
        transform_scene.transform_props.parent_screen = context.screen.name

        # Set up scene frames
        if len(self.source_strips) == 1:
            strip = self.source_strips[0]
            transform_scene.frame_start = strip.animation_offset_start + 1
            transform_scene.frame_end = strip.animation_offset_start + max(
                strip.frame_duration, strip.frame_final_duration
            )
            transform_scene.use_preview_range = True
            transform_scene.frame_preview_start = strip.frame_offset_start + \
                strip.animation_offset_start + 1
            transform_scene.frame_preview_end = \
                transform_scene.frame_preview_start \
                + strip.frame_final_duration - 1
            transform_scene.frame_current = transform_scene.frame_preview_start
        else:
            transform_scene.frame_start = 1
            transform_scene.frame_end = \
                self.transform_strip_end - self.transform_strip_start

        # Copy render settings
        transform_scene.render.resolution_x = seq_scene.render.resolution_x
        transform_scene.render.resolution_y = seq_scene.render.resolution_y
        transform_scene.render.resolution_percentage = 100
        transform_scene.render.fps = seq_scene.render.fps

        # Add scene strip
        transform_strip = se.sequences.new_scene(
            transform_scene.name, transform_scene,
            self.transform_strip_channel,
            self.transform_strip_start
        )

        # Position strip
        if len(self.source_strips) == 1:
            transform_strip.frame_start = self.source_strips[0].frame_start
            transform_strip.frame_offset_start = \
                self.source_strips[0].frame_offset_start
            transform_strip.frame_offset_end = \
                self.source_strips[0].frame_offset_end

        # Reset channel
        transform_strip.channel = self.transform_strip_channel

        # Find first screen containing default
        screen_found = False
        for screen in bpy.data.screens:
            if "default" in screen.name.lower():
                transform_scene.transform_props.edit_screen = screen.name
                screen_found = True
                break

        # Find first screen containing 3d else
        if not screen_found:
            for screen in bpy.data.screens:
                if "3d" in screen.name.lower():
                    transform_strip.transform_props.edit_screen = screen.name
                    break

        # Select new strip
        for strip in context.selected_sequences:
            strip.select = False
        transform_strip.select = True
        se.active_strip = transform_strip

        # Set up transform scene
        context.screen.scene = transform_scene
        transform_scene.render.alpha_mode = 'TRANSPARENT'

        # Add camera
        bpy.ops.object.camera_add()
        transform_scene.camera = transform_scene.objects.active
        transform_scene.camera.location.z = \
            transform_scene.camera.data.lens / 16

        # Add image planes
        if len(self.source_strips) == 1:
            create_plane(self.source_strips[0], False)
        else:
            for strip in self.source_strips:
                create_plane(strip, True)

        # Switch back to sequencer scene
        context.screen.scene = seq_scene

        return {'FINISHED'}

    # Get source strips
    def get_source_strips(self, context):
        # Get selected strips
        source_strips = context.selected_sequences

        # Put active strip to end
        for strip in source_strips:
            if strip == context.scene.sequence_editor.active_strip:
                source_strips.remove(strip)
                source_strips.append(strip)
                break

        # Return source strips
        return source_strips

# Rendered text button
def transform_3d_button(self, context):
    self.layout.operator(
        Transform3DEffectAddOperator.bl_idname,
        text="Transform 3D",
        icon='PLUGIN'
    )

### Rendered text strip panel ###
#################################

# Switch to transform operator
class SwitchToTranform3DOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "vse_transform3d.switch_to_transform_3d_editing"
    bl_label = "Switch to Tranform 3D editing"
    bl_description = "Switch to transform 3D scene editing"

    # Show only for transform strips
    @classmethod
    def poll(self, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (strip is not None and strip.type == 'SCENE' and \
            strip.scene is not None and \
            strip.scene.transform_props.is_transform_scene)

    # Switch scene
    def invoke(self, context, event):
        strip = context.scene.sequence_editor.active_strip

        # Set scene properties
        strip.scene.transform_props.parent_screen = context.screen.name

        # Update preview range
        if strip.scene.use_preview_range:
            strip.scene.frame_preview_start = strip.scene.frame_start + \
                strip.frame_offset_start
            strip.scene.frame_preview_end = strip.scene.frame_preview_start + \
                strip.frame_final_duration - 1

        # Switch to transform screen
        switch_screen(context, strip.scene.transform_props.edit_screen)

        # Switch to scene
        context.screen.scene = strip.scene

        return {'FINISHED'}

# Remove transform strip operator
class RemoveTransform3DStripOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "vse_transform3d.remove_transform_3d_strip"
    bl_label = "Remove Transform 3D strip"
    bl_description = "Remove transform 3D scene and sequencer strip"

    # Show only for transform Strips
    @classmethod
    def poll(cls, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (strip is not None and strip.type == 'SCENE' and \
            strip.scene is not None and \
            strip.scene.transform_props.is_transform_scene)

    # Show confirmation dialog
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    # Remove scene and strip
    def execute(self, context):
        strip = context.scene.sequence_editor.active_strip

        # Remove scene
        bpy.data.scenes.remove(strip.scene)

        # Remove strip (taking groups into account)
        selected = context.selected_sequences
        for seq in selected:
            seq.select = False
        strip.select = True
        bpy.ops.sequencer.delete()
        for seq in selected:
            seq.select = True

        return {'FINISHED'}

# Transform strip panel
class Transform3DStripPanel(bpy.types.Panel):
    # Meta data
    bl_label = "Transform 3D Strip"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"

    # Show only for transform strips
    @classmethod
    def poll(self, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (strip is not None and strip.type =='SCENE' and \
            strip.scene is not None and \
            strip.scene.transform_props.is_transform_scene)

    # Draw panel
    def draw(self, context):
        strip = context.scene.sequence_editor.active_strip
        
        # Editing
        self.layout.operator(
            SwitchToTranform3DOperator.bl_idname, text="Edit Transformation",
            icon='TEXT'
        )
        self.layout.prop(
            strip.scene.transform_props, 'edit_screen', text="",
            icon='SPLITSCREEN'
        )
        self.layout.prop(strip.scene.render, 'resolution_percentage')
        self.layout.operator(
            RemoveTransform3DStripOperator.bl_idname, text="Remove", icon='X'
        )

### Text scene panel ###
#############################

# Switch to sequence editor operator
class SwitchToSequenceEditorOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "vse_transform3d.switch_to_sequence_editor"
    bl_label = "Back to Sequencer"
    bl_description = "Switch back to the Sequence Editor"

    # Show only for tranform scenes
    @classmethod
    def poll(self, context):
        return context.scene.transform_props.is_transform_scene

    # Switch scene
    def invoke(self, context, event):
        # Get transform properties
        transform_props = context.scene.transform_props

        # Switch screen
        switch_screen(context, transform_props.parent_screen)

        # Switch to scene
        scene = get_scene(transform_props.parent_scene_id)
        if scene is not None:
            context.screen.scene = scene
        else:
            self.report({'ERROR'}, "Sequence editing scene missing")

        return {'FINISHED'}

# Switch to sequence editor Panel
class TransformScenePanel(bpy.types.Panel):
    # Meta data
    bl_label = "Transform Scene"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    # Show only for text strips
    @classmethod
    def poll(self, context):
        return context.scene.transform_props.is_transform_scene

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

    # Register scene properties
    bpy.types.Scene.transform_props = bpy.props.PointerProperty(
        type=SceneTransform3DProps
    )

    # Add button
    bpy.types.SEQUENCER_MT_add_effect.append(transform_3d_button)

# Unregister module
def unregister():
    # Unregister module
    bpy.utils.unregister_module(__name__)

    # Unregister scene properties
    del bpy.types.Scene.transform_props

    # Remove button
    bpy.types.SEQUENCER_MT_add_effect.remove(transform_3d_button)

# Register if executed as script
if __name__ == '__main__':
    register()
