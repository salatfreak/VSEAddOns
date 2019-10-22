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
    "name": "Add Composite Effect",
    "author": "Salatfreak",
    "version": (0, 2),
    "blender": (2, 80, 0),
    "location": "Video Sequence Editor > Add > Effect Strip > Composite",
    "description": "Adds Composite effect to Image and Movie Strips",
    "warning": "",
    "wiki_url": "",
    "category": "Sequencer"
}

# Constants
MAX_CHANNEL = 32

# Import modules
import bpy
from os import path
import re
import math
from functools import reduce
from mathutils import Vector

### Helper functions ###
########################
 
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

# Composite scene property group
class SceneCompositeProps(bpy.types.PropertyGroup):
    # Is composite scene property
    is_comp_scene: bpy.props.BoolProperty(
        name="Is Composite Scene", default=False
    )
    
    # Get scenes
    def get_screens(self, context):
        return [(scr.name, scr.name, "") for scr in bpy.data.screens]

    # Mask screen property
    mask_screen: bpy.props.EnumProperty(name="Mask screen", items=get_screens)

### Effect operators ###
########################

# Add composite operators
class EffectAddOperator():
    # Meta data
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
        self.comp_strip_start = max(
            [strip.frame_final_start for strip in self.source_strips]
        )
        self.comp_strip_end = min(
            [strip.frame_final_end for strip in self.source_strips]
        )

        # Require shared frames
        if self.comp_strip_start >= self.comp_strip_end:
            self.report({'ERROR'}, "Strips must have shared frames")
            return {'CANCELLED'}

        # Get following channel
        highest_channel = max(
            [strip.channel for strip in self.source_strips]
        )
        self.comp_strip_channel = (highest_channel + 1) % (MAX_CHANNEL + 1)

        # Get sequences per channel
        sequences = get_sequence_list(context.scene, self.source_strips[0])
        channel_seqs = [[] for i in range(MAX_CHANNEL + 1)]
        for seq in sequences:
            channel_seqs[seq.channel].append(seq)

        # Find first fitting channel
        channel_found = False
        while self.comp_strip_channel != highest_channel:
            # Count up on conflict
            if any(not(seq.frame_final_end < self.comp_strip_start or \
                self.comp_strip_end < seq.frame_final_start)
                    for seq in channel_seqs[self.comp_strip_channel]):
                self.comp_strip_channel = \
                    (self.comp_strip_channel % MAX_CHANNEL) + 1
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

    # Create effect
    def execute(self, context):
        # Get sequence editor
        se = context.scene.sequence_editor

        # Create node
        def create_node(strip, multi):
            # Create node
            node = nodes.new('CompositorNodeImage')

            # Get file path
            if strip.type == 'MOVIE':
                image_source = 'MOVIE'
                image_path = strip.filepath
            else:
                image_source = 'SEQUENCE' if len(strip.elements) > 1 else 'FILE'
                image_path = path.join(
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

            # Set up node
            node.image = image
            node.name = node.label = strip.name

            # Set up image
            img_offset = 0
            if strip.type == 'MOVIE':
                # Auto refresh frames
                node.use_auto_refresh = True
            elif len(strip.elements) > 1:
                # Match image file
                match = img_seq_re.match(strip.elements[0].filename)

                # Set offset
                if match is not None:
                    img_offset = int(
                        match.string[match.regs[2][0]:match.regs[2][1]]
                    ) - 1

                # Auto refresh frames
                node.use_auto_refresh = True

            # Set up frames
            if multi:
                node.frame_offset = self.comp_strip_start - strip.frame_start \
                    + strip.animation_offset_start + img_offset
                node.frame_duration = self.comp_strip_end \
                    - self.comp_strip_start
            else:
                node.frame_start = strip.animation_offset_start + 1
                node.frame_offset = strip.animation_offset_start + img_offset
                node.frame_duration = strip.frame_duration

            # Return node
            return node

        # Add new scene
        comp_scene = bpy.data.scenes.new(self.comp_scene_name)
        comp_scene.sf_comp_props.is_comp_scene = True
        comp_scene.use_nodes = True

        # Set up scene frames
        if len(self.source_strips) == 1:
            strip = self.source_strips[0]
            comp_scene.frame_start = strip.animation_offset_start + 1
            comp_scene.frame_end = strip.animation_offset_start + max(
                strip.frame_duration, strip.frame_final_duration
            )
            comp_scene.use_preview_range = True
            comp_scene.frame_preview_start = strip.frame_offset_start + \
                strip.animation_offset_start + 1
            comp_scene.frame_preview_end = comp_scene.frame_preview_start + \
                strip.frame_final_duration - 1
            comp_scene.frame_current = comp_scene.frame_preview_start
        else:
            comp_scene.frame_start = 1
            comp_scene.frame_end = self.comp_strip_end - self.comp_strip_start

        # Copy render settings
        comp_scene.render.resolution_x = context.scene.render.resolution_x
        comp_scene.render.resolution_y = context.scene.render.resolution_y
        comp_scene.render.resolution_percentage = 100
        comp_scene.render.fps = context.scene.render.fps

        # Add scene strip
        comp_strip = se.sequences.new_scene(
            comp_scene.name, comp_scene,
            self.comp_strip_channel,
            self.comp_strip_start
        )

        # Position for single strip
        if len(self.source_strips) == 1:
            comp_strip.frame_start = self.source_strips[0].frame_start
            comp_strip.frame_offset_start = \
                self.source_strips[0].frame_offset_start
            comp_strip.frame_offset_end = self.source_strips[0].frame_offset_end
            
        # Reset channel
        comp_strip.channel = self.comp_strip_channel

        # Set edit screen for scene tools addon
        if hasattr(comp_scene, 'sf_scene_props'):
            for screen in bpy.data.screens:
                if "composit" in screen.name.lower():
                    comp_scene.sf_scene_props.edit_screen = screen.name
                    break

        # Set mask screen
        for screen in bpy.data.screens:
            if "tracking" in screen.name.lower() \
            or "mask" in screen.name.lower():
                comp_scene.sf_comp_props.mask_screen = screen.name
                break

        # Select new strip
        for strip in context.selected_sequences:
            strip.select = False
        comp_strip.select = True
        se.active_strip = comp_strip

        # Reset nodes
        nodes = comp_scene.node_tree.nodes
        for node in nodes:
            nodes.remove(node)

        # Add input nodes
        input_nodes = []
        if len(self.source_strips) == 1:
            input_nodes.append(create_node(self.source_strips[0], False))
        else:
            for strip in self.source_strips:
                input_nodes.append(create_node(strip, True))

        # Set up nodes
        self.set_up_nodes(comp_scene, input_nodes)

        return {'FINISHED'}

    # Get source strips
    def get_source_strips(self, context):
        # Get selected strips
        source_strips = context.selected_sequences or []

        # Put active strip to end
        for strip in source_strips:
            if strip == context.scene.sequence_editor.active_strip:
                source_strips.remove(strip)
                source_strips.append(strip)
                break

        # Return source strips
        return source_strips

    # Set up nodes
    def set_up_nodes(self, scene, input_nodes):
        # Get node tree
        node_tree = scene.node_tree
        
        # Position nodes and create scale nodes
        scale_nodes = []
        node_loc = Vector((0, 0))
        for node in input_nodes:
            # Position node
            node.location = Vector(node_loc)

            # Create scale node
            scale_node = node_tree.nodes.new('CompositorNodeScale')
            scale_node.name = "Scale_"+ node.name
            scale_node.label = "Scale "+ node.name
            scale_node.space = 'RENDER_SIZE'
            scale_node.location = node_loc + Vector((180, 0))

            # Connect scale node
            node_tree.links.new(
                node.outputs['Image'], scale_node.inputs['Image']
            )

            # Store scale node
            scale_nodes.append(scale_node)

            # Calculate next node location
            node_loc -=  Vector((0, 360))

        return scale_nodes

# Composite effect
class CompositeEffectAddOperator(bpy.types.Operator, EffectAddOperator):
    # Meta data
    bl_idname="sf_addons.composite_effect_add"
    bl_label="Add Composite Effect"

    # Prepare data
    def invoke(self, context, event):
        # Generate compositing scene name
        self.comp_scene_name = "Composite_"+ \
            self.get_source_strips(context)[-1].name

        # Initialize general effect operator
        return EffectAddOperator.invoke(self, context, event)

    # Set up nodes
    def set_up_nodes(self, scene, input_nodes):
        # Set up input and scale nodes
        scale_nodes = EffectAddOperator.set_up_nodes(self, scene, input_nodes)

        # Get node tree
        node_tree = scene.node_tree

        # Add composite node
        composite_node = node_tree.nodes.new('CompositorNodeComposite')
        composite_node.location = scale_nodes[0].location + Vector((180, 0))

        # Connect nodes
        node_tree.links.new(
            scale_nodes[0].outputs['Image'],
            composite_node.inputs['Image']
        )

        # Add viewer node
        viewer_node = node_tree.nodes.new('CompositorNodeViewer')
        viewer_node.location = composite_node.location + Vector((0, -160))

        # Connect nodes
        node_tree.links.new(
            scale_nodes[0].outputs['Image'],
            viewer_node.inputs['Image']
        )

        # Deselect all nodes
        for node in node_tree.nodes:
            node.select = False

        # Center nodes
        for node in node_tree.nodes:
            node.location += Vector((0, 640))

# Composite button
def composite_button(self, context):
    self.layout.operator(
        CompositeEffectAddOperator.bl_idname,
        text="Composite",
        icon='PLUGIN'
    )

# Keying effect
class KeyingEffectAddOperator(bpy.types.Operator, EffectAddOperator):
    # Meta data
    bl_idname="sf_addons.keying_effect_add"
    bl_label="Add Keying Effect"

    # Prepare data
    def invoke(self, context, event):
        # Generate compositing scene name
        self.comp_scene_name = "Keying_"+ context.selected_sequences[0].name

        # Initialize general effect operator
        return EffectAddOperator.invoke(self, context, event)

    # Get source strips
    def get_source_strips(self, context):
        return EffectAddOperator.get_source_strips(self, context)[-1:]

    # Set up nodes
    def set_up_nodes(self, scene, input_nodes):
        # Set up input and scale nodes
        scale_node = EffectAddOperator.set_up_nodes(self, scene, input_nodes)[0]

        # Get node tree
        node_tree = scene.node_tree

        # Add mask node
        mask_node = node_tree.nodes.new('CompositorNodeMask')
        mask_node.location = scale_node.location + Vector((-180, -360))

        # Add invert node
        invert_node = node_tree.nodes.new('CompositorNodeInvert')
        invert_node.location = scale_node.location + Vector((0, -360))

        # Connect nodes
        node_tree.links.new(
            mask_node.outputs['Mask'], invert_node.inputs['Color']
        )

        # Add keying node
        keying_node = node_tree.nodes.new('CompositorNodeKeying')
        keying_node.location = scale_node.location + Vector((180, 0))

        # Connect nodes
        node_tree.links.new(
            scale_node.outputs['Image'], keying_node.inputs['Image']
        )

        # Add alpha converter node
        alpha_node = node_tree.nodes.new('CompositorNodePremulKey')
        alpha_node.location = keying_node.location + Vector((180, 0))

        # Connect nodes
        node_tree.links.new(
            keying_node.outputs['Image'], alpha_node.inputs['Image']
        )

        # Add composite node
        composite_node = node_tree.nodes.new('CompositorNodeComposite')
        composite_node.location = alpha_node.location + Vector((180, 0))

        # Connect nodes
        node_tree.links.new(
            alpha_node.outputs['Image'], composite_node.inputs['Image']
        )

        # Add viewer node
        viewer_node = node_tree.nodes.new('CompositorNodeViewer')
        viewer_node.location = composite_node.location + Vector((0, -160))

        # Connect nodes
        node_tree.links.new(
            alpha_node.outputs['Image'], viewer_node.inputs['Image']
        )

        # Deselect all nodes
        for node in node_tree.nodes:
            node.select = False

        # Center nodes
        for node in node_tree.nodes:
            node.location += Vector((-160, 520))

# Keying button
def keying_button(self, context):
    self.layout.operator(
        KeyingEffectAddOperator.bl_idname,
        text="Keying",
        icon='PLUGIN'
    )

# Pixelize effect
class PixelizeEffectAddOperator(bpy.types.Operator, EffectAddOperator):
    # Meta data
    bl_idname="sf_addons.pixelize_effect_add"
    bl_label="Add Pixelize Effect"

    # Prepare data
    def invoke(self, context, event):
        # Generate compositing scene name
        self.comp_scene_name = "Pixelize_"+ context.selected_sequences[0].name

        # Initialize general effect operator
        return EffectAddOperator.invoke(self, context, event)

    # Get source strips
    def get_source_strips(self, context):
        return EffectAddOperator.get_source_strips(self, context)[-1:]

    # Set up nodes
    def set_up_nodes(self, scene, input_nodes):
        # Set up input and scale nodes
        scale_node = EffectAddOperator.set_up_nodes(self, scene, input_nodes)[0]

        # Get node tree
        node_tree = scene.node_tree

        # Add size node
        size_node = node_tree.nodes.new('CompositorNodeMath')
        size_node.name = size_node.label = 'Size'
        size_node.operation = 'MULTIPLY'
        size_node.inputs[0].default_value = 0.305
        size_node.location = scale_node.location + Vector((-180, 180))
        
        # Resolution percentage driver
        res_driver = size_node.inputs[1].driver_add('default_value').driver
        res_driver.type = 'AVERAGE'
        res_variable = res_driver.variables.new()
        res_variable.name = "scale"
        res_variable.type = 'SINGLE_PROP'
        res_variable.targets[0].id_type = 'SCENE'
        res_variable.targets[0].id = scene
        res_variable.targets[0].data_path = 'render.resolution_percentage'

        # Add mask node
        mask_node = node_tree.nodes.new('CompositorNodeMask')
        mask_node.location = size_node.location + Vector((0, 220))

        # Create pixelize group if not existent
        if 'Pixelize' not in bpy.data.node_groups:
            # Create group
            pixelize = bpy.data.node_groups.new(
                "Pixelize", 'CompositorNodeTree'
            )

            # Add group input node
            input_node = pixelize.nodes.new('NodeGroupInput')

            # Add math node
            divide_node = pixelize.nodes.new('CompositorNodeMath')
            divide_node.operation = 'DIVIDE'
            divide_node.inputs[0].default_value = 1.0
            divide_node.location = input_node.location + Vector((180, -140))

            # Add scale down node
            scale_down_node = pixelize.nodes.new('CompositorNodeScale')
            scale_down_node.location = divide_node.location + Vector((180, 100))

            # Connect nodes
            pixelize.links.new(
                input_node.outputs[0], scale_down_node.inputs['Image']
            )
            pixelize.links.new(input_node.outputs[1], divide_node.inputs[1])
            pixelize.links.new(
                divide_node.outputs['Value'], scale_down_node.inputs['X']
            )
            pixelize.links.new(
                divide_node.outputs['Value'], scale_down_node.inputs['Y']
            )

            # Add pixelate node
            pixelate_node = pixelize.nodes.new('CompositorNodePixelate')
            pixelate_node.location = scale_down_node.location + Vector((180, 0))

            # Connect nodes
            pixelize.links.new(
                scale_down_node.outputs['Image'], pixelate_node.inputs['Color']
            )

            # Add scale up node
            scale_up_node = pixelize.nodes.new('CompositorNodeScale')
            scale_up_node.location = pixelate_node.location + Vector((180, 200))

            # Connect nodes
            pixelize.links.new(
                pixelate_node.outputs['Color'], scale_up_node.inputs['Image']
            )
            pixelize.links.new(
                input_node.outputs['Value'], scale_up_node.inputs['X']
            )
            pixelize.links.new(
                input_node.outputs['Value'], scale_up_node.inputs['Y']
            )

            # Add group output node
            output_node = pixelize.nodes.new('NodeGroupOutput')
            output_node.location = scale_up_node.location + Vector((180, -160))

            # Connect nodes
            pixelize.links.new(
                scale_up_node.outputs['Image'], output_node.inputs[0]
            )

            # Center nodes
            for node in pixelize.nodes:
                node.location += Vector((-60, 80))
        else:
            pixelize = bpy.data.node_groups['Pixelize']

        # Add pixelize node
        pixelize_movie_node = node_tree.nodes.new('CompositorNodeGroup')
        pixelize_movie_node.node_tree = pixelize
        pixelize_movie_node.location = scale_node.location + Vector((180, 80))

        # Connect nodes
        node_tree.links.new(
            scale_node.outputs['Image'],
            pixelize_movie_node.inputs['Image']
        )
        node_tree.links.new(
            size_node.outputs['Value'], pixelize_movie_node.inputs['Value']
        )

        # Add pixelize node
        pixelize_mask_node = node_tree.nodes.new('CompositorNodeGroup')
        pixelize_mask_node.node_tree = pixelize
        pixelize_mask_node.location = pixelize_movie_node.location \
            + Vector((0, 160))

        # Connect nodes
        node_tree.links.new(
            mask_node.outputs['Mask'], pixelize_mask_node.inputs['Image']
        )
        node_tree.links.new(
            size_node.outputs['Value'], pixelize_mask_node.inputs['Value']
        )

        # Add mix node
        mix_node = node_tree.nodes.new('CompositorNodeMixRGB')
        mix_node.use_alpha = True
        mix_node.location = pixelize_mask_node.location + Vector((180, -40))

        # Connect nodes
        node_tree.links.new(
            pixelize_mask_node.outputs['Image'], mix_node.inputs['Fac']
        )
        node_tree.links.new(
            scale_node.outputs['Image'], mix_node.inputs[1]
        )
        node_tree.links.new(
            pixelize_movie_node.outputs['Image'], mix_node.inputs[2]
        )

        # Add composite node
        composite_node = node_tree.nodes.new('CompositorNodeComposite')
        composite_node.location = mix_node.location + Vector((180, 0))

        # Connect nodes
        node_tree.links.new(
            mix_node.outputs['Image'], composite_node.inputs['Image']
        )

        # Add viewer node
        viewer_node = node_tree.nodes.new('CompositorNodeViewer')
        viewer_node.location = composite_node.location + Vector((0, -160))

        # Connect nodes
        node_tree.links.new(
            mix_node.outputs['Image'], viewer_node.inputs['Image']
        )

        # Deselect all nodes
        for node in node_tree.nodes:
            node.select = False

        # Center nodes
        for node in node_tree.nodes:
            node.location += Vector((-160, 260))

# Pixelize button
def pixelize_button(self, context):
    self.layout.operator(
        PixelizeEffectAddOperator.bl_idname,
        text="Pixelize",
        icon='PLUGIN'
    )

### Transform3D Operator ###
############################

# Add transform effect operator
class Transform3DEffectAddOperator(bpy.types.Operator):
    # Meta data
    bl_idname="sf_addons.transform_3d_effect_add"
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
        def create_plane(strip, y_offset, multi):
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
            image_plane.rotation_euler[0] = math.radians(90)
            bpy.ops.object.transform_apply(rotation=True, scale=True)
            image_plane.location.y = y_offset

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
                image_path = path.join(
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

        # Add new scene
        transform_scene = bpy.data.scenes.new(
            "Transform3D_"+ self.source_strips[-1].name
        )

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

        # Set edit screen for scene tools addon
        if hasattr(transform_scene, 'sf_scene_props'):
            # Find first screen containing default
            screen_found = False
            for screen in bpy.data.screens:
                if "default" in screen.name.lower():
                    transform_scene.sf_scene_props.edit_screen = screen.name
                    screen_found = True
                    break

            # Find first screen containing 3d else
            if not screen_found:
                for screen in bpy.data.screens:
                    if "3d" in screen.name.lower():
                        transform_scene.sf_scene_props.edit_screen = screen.name
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
        transform_scene.camera.location.y = \
            - transform_scene.camera.data.lens / 16
        transform_scene.camera.rotation_euler[0] = math.radians(90)

        # Add image planes
        if len(self.source_strips) == 1:
            create_plane(self.source_strips[0], 0, False)
        else:
            for offset, strip in enumerate(self.source_strips):
                create_plane(strip, offset * 0.1, True)

        # Switch back to sequencer scene
        context.screen.scene = seq_scene

        return {'FINISHED'}

    # Get source strips
    def get_source_strips(self, context):
        # Get selected strips
        source_strips = context.selected_sequences or []

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

### Composite scene Panel ###
#############################

# Switch to mask editing
class SwitchToMaskOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.switch_to_composite_mask"
    bl_label = "Edit Mask"
    bl_description = "Edit mask for compositing"

    # Show only for composite strips with valid 
    @classmethod
    def poll(self, context):
        return context.scene.sf_comp_props.is_comp_scene

    # Switch scene
    def invoke(self, context, event):
        # Store composite scene
        composite_scene = context.scene

        # Get composite scene
        sf_comp_props = context.scene.sf_comp_props

        # Switch to screen
        switch_screen(context, sf_comp_props.mask_screen)

        # Switch to scene
        context.screen.scene = composite_scene

        # Find image nodes
        image_nodes = list(filter(
            lambda n: n.type == 'IMAGE', composite_scene.node_tree.nodes
        ))

        # Find mask nodes
        mask_nodes = list(filter(
            lambda n: n.type == 'MASK', composite_scene.node_tree.nodes
        ))

        # Find clip area
        clip_area = None
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR' and area.spaces[0].view == 'CLIP':
                clip_area = area
                break

        # Show clip
        if clip_area is not None:
            if len(image_nodes) in {1, 2} and \
                image_nodes[0].image is not None:
                # Find clip
                mask_clip = None
                for clip in bpy.data.movieclips:
                    if clip.filepath == image_nodes[0].image.filepath:
                        mask_clip = clip
                        break

                # Load clip if not found
                if mask_clip is None:
                    mask_clip = bpy.data.movieclips.load(
                        image_nodes[0].image.filepath
                    )

                # Set clip
                clip_area.spaces[0].clip = mask_clip

            # Set up mask
            if clip_area.spaces[0].clip is not None:
                clip_area.spaces[0].mode = 'MASK'

                # Set up mask if single mask node
                if len(mask_nodes) == 1:
                    # Create mask node if none selected
                    if mask_nodes[0].mask is None:
                        mask_nodes[0].mask = bpy.data.masks.new(
                            composite_scene.name
                        )

                    # Edit mask
                    clip_area.spaces[0].mask = mask_nodes[0].mask
        else:
            self.report({'ERROR'}, "Mask screen missing")

        return {'FINISHED'}

# Switch to sequence editor Panel
class NODE_EDITOR_PT_composite_scene_panel(bpy.types.Panel):
    # Meta data
    bl_label = "Composite Scene"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"

    # Show only for composite strips
    @classmethod
    def poll(self, context):
        return SwitchToMaskOperator.poll(context)

    # Draw panel
    def draw(self, context):
        self.layout.operator(SwitchToMaskOperator.bl_idname, icon='MOD_MASK')
        self.layout.prop(
            context.scene.sf_comp_props, 'mask_screen', text="",
            icon='SPLITSCREEN'
        )

### Module registration ###
###########################AA

# Register module
def register():
    # Register module

    bpy.utils.register_class(SceneCompositeProps)
    #bpy.utils.register_class(EffectAddOperator)
    bpy.utils.register_class(CompositeEffectAddOperator)
    bpy.utils.register_class(KeyingEffectAddOperator)
    bpy.utils.register_class(PixelizeEffectAddOperator)
    bpy.utils.register_class(Transform3DEffectAddOperator)
    bpy.utils.register_class(SwitchToMaskOperator)
    bpy.utils.register_class(NODE_EDITOR_PT_composite_scene_panel)

    # Register scene properties
    bpy.types.Scene.sf_comp_props = bpy.props.PointerProperty(
        type=SceneCompositeProps
    )

    # Add buttons
    bpy.types.SEQUENCER_MT_add_effect.append(composite_button)
    bpy.types.SEQUENCER_MT_add_effect.append(keying_button)
    bpy.types.SEQUENCER_MT_add_effect.append(pixelize_button)
    bpy.types.SEQUENCER_MT_add_effect.append(transform_3d_button)

# Unregister module
def unregister():
    # Unregister module
    bpy.utils.unregister_class(SceneCompositeProps)
    #bpy.utils.unregister_class(EffectAddOperator)
    bpy.utils.unregister_class(CompositeEffectAddOperator)
    bpy.utils.unregister_class(KeyingEffectAddOperator)
    bpy.utils.unregister_class(PixelizeEffectAddOperator)
    bpy.utils.unregister_class(Transform3DEffectAddOperator)
    bpy.utils.unregister_class(SwitchToMaskOperator)
    bpy.utils.unregister_class(NODE_EDITOR_PT_composite_scene_panel)

    # Unregister scene properties
    del bpy.types.Scene.sf_comp_props

    # Remove buttons
    bpy.types.SEQUENCER_MT_add_effect.remove(composite_button)
    bpy.types.SEQUENCER_MT_add_effect.remove(keying_button)
    bpy.types.SEQUENCER_MT_add_effect.remove(pixelize_button)
    bpy.types.SEQUENCER_MT_add_effect.remove(transform_3d_button)

# Register if executed as script
if __name__ == '__main__':
    register()
