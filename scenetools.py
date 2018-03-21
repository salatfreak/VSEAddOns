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
    "name": "Scene Tools",
    "author": "Salatfreak",
    "version": (0, 1),
    "blender": (2, 75),
    "location": "Video Sequence Editor > Properties > Scene Tools",
    "description": "Adjust all scenes resolution percentage and render out "\
        "scene strips",
    "warning": "",
    "wiki_url": "",
    "category": "Sequencer"
}

# Constants
MAX_CHANNEL = 32
RENDER_FILE_NAME = "renderSceneStrip.blend"
RENDER_DIR = "//renders/scenes"

# Import modules
import bpy
from uuid import uuid4
from base64 import b64encode
import subprocess
import threading
from os import path, listdir, makedirs, remove as remove_file
from shutil import rmtree, move as move_file
import re
import json
from urllib import parse

### Prepare RegExp ###
######################

frame_re = re.compile("^Fra:(\d+)")

### Helper functions ###
########################

# Make scene ID unique
def uniquify_scene(context, scene_id):
    first_found = False
    for scene in context.scenes:
        if scene.sf_scene_props.id == scene_id:
            if not first_found:
                first_found = True
            else:
                scene.sf_scene_props.id = generate_uid()

# Make strip ID unique
def uniquify_strip(context, strip_id):
    first_found = False
    for scene in context.scenes:
        if scene.use_sequencer:
            for strip in scene.sequence_editor.sequences_all:
                if strip.sf_scene_props.id == strip_id:
                    if not first_found:
                        first_found = True
                    else:
                        scene.sf_scene_props.id = generate_uid()

# Get scene from ID
def get_scene(scene_id):
    # Find and return scene with matching ID
    for scene in bpy.data.scenes:
        if scene.sf_scene_props.id == scene_id:
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

# Generate unique and filesystem safe id
def generate_uid():
    return b64encode(uuid4().bytes, altchars=b'_-').decode('ascii').rstrip('=')

### Object properties ###
#########################

# Scene properties
class SceneProperties(bpy.types.PropertyGroup):
    # Scene id
    id = bpy.props.StringProperty(name="Unique ID", default="")

    # VSE scene id
    vse_scene_id = bpy.props.StringProperty(name="VSE Scene ID", default="")

    # Get screens
    def get_screens(self, context):
        return [(scr.name, scr.name, "") for scr in bpy.data.screens]

    # VSE screen
    vse_screen = bpy.props.EnumProperty(name="VSE Screen", items=get_screens)

    # Edit screen
    edit_screen = bpy.props.EnumProperty(name="Edit Screen", items=get_screens)

# Strip properties
class StripProperties(bpy.types.PropertyGroup):
    # Strip id
    id = bpy.props.StringProperty(name="Unique ID", default="")

    # Scene id
    scene_id = bpy.props.StringProperty(name="VSE Scene ID", default="")

    # Use sequencer
    use_sequencer = bpy.props.BoolProperty(name="Use Sequencer")

    # Camera override
    scene_camera = bpy.props.StringProperty(name="Camera Override")

    # Show grease pencil
    use_grease_pencil = bpy.props.BoolProperty(name="Show Grease Pencil")

    # Render progress
    render_progress = bpy.props.IntProperty(name="Render Progress", default=-1)

    def get_progress(self):
        return self.render_progress

    render_display = bpy.props.IntProperty(
        min=0, max=100, name="Render Progress", subtype='PERCENTAGE',
        description="Scene render progress", get=get_progress
    )

    abort_render = bpy.props.BoolProperty(
        name="Render Abort Requested", default=False
    )

### Distribute resolution percentage ###
########################################

# Distribute resolution percentage operator
class DistributeResolutionPercentageOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.distribute_resolution_percentage"
    bl_label = "Distribute Resolution Percentage"
    bl_description = "Copy resolution percentage to all other scenes"
    bl_options = {'REGISTER', 'UNDO'}

    # Distribute resolution percentage
    def invoke(self, context, event):
        for scene in bpy.data.scenes:
            scene.render.resolution_percentage = \
                context.scene.render.resolution_percentage

        # Redraw UI
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        return {'FINISHED'}

# Distribute resolution percentage button
def distribute_button(self, context):
    self.layout.operator(DistributeResolutionPercentageOperator.bl_idname)

### Scene tools panel ###
#############################

# Edit scene operator
class EditSceneOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.edit_scene"
    bl_label = "Edit scene"
    bl_description = "Switch to scene editing"

    # Show only for scene strips
    @classmethod
    def poll(cls, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (
            strip is not None \
            and strip.type == 'SCENE' \
            and strip.scene is not None
        )

    # Edit scene
    def invoke(self, context, event):
        strip = context.scene.sequence_editor.active_strip
        sf_scene_props = context.scene.sf_scene_props

        # Set scene IDs
        if sf_scene_props.id == "":
            sf_scene_props.id = generate_uid()

        if strip.scene.sf_scene_props.id == "":
            strip.scene.sf_scene_props.id = generate_uid()

        # Store vse sceen and screen
        strip.scene.sf_scene_props.vse_scene_id = sf_scene_props.id
        strip.scene.sf_scene_props.vse_screen = context.screen.name

        # Update preview range
        strip.scene.frame_preview_start = strip.scene.frame_start + \
            strip.frame_offset_start
        strip.scene.frame_preview_end = strip.scene.frame_preview_start + \
            strip.frame_final_duration - 1

        # Switch to editing screen
        switch_screen(context, strip.scene.sf_scene_props.edit_screen)

        # Switch to scene
        context.screen.scene = strip.scene

        return {'FINISHED'}

# Render task
class RenderTask():
    # Initialize task
    def __init__(self, filepath, strip):
        # Set scene ID
        if strip.sf_scene_props.id == "":
            strip.sf_scene_props.id = generate_uid()

        # Set up properties
        camera = strip.scene_camera or strip.scene.camera
        self.strip = strip
        self.filepath = filepath
        self.scene_name = strip.scene.name
        self.camera_name = camera.name if camera is not None else ""
        self.use_sequence = strip.use_sequence
        self.output = path.join(
            bpy.path.abspath(RENDER_DIR), strip.sf_scene_props.id, ""
        )
        self.frame_start = strip.scene.frame_preview_start \
            if strip.scene.use_preview_range else strip.scene.frame_start
        self.frame_end = strip.scene.frame_preview_end \
            if strip.scene.use_preview_range else strip.scene.frame_end

# Render thread
class RenderThread(threading.Thread):
    # Set up thread
    def __init__(self, task):
        threading.Thread.__init__(self)
        self.task = task
        self._frame = task.frame_start - 1
        self._stop_event = threading.Event()
        self._lock = threading.RLock()

    # Render
    def run(self):
        # Remove existing backup files
        backup_path = path.join(self.task.output, 'backup')
        if path.exists(backup_path):
            if path.isdir(backup_path) and not path.islink(backup_path):
                rmtree(backup_path)
            else:
                remove_file(backup_path)

        # Create backup
        makedirs(backup_path)
        for file_name in listdir(self.task.output):
            file_path = path.join(self.task.output, file_name)
            if path.isfile(file_path):
                move_file(file_path, path.join(backup_path, file_name))

        # Start rendering process
        self.proc = subprocess.Popen([
            bpy.app.binary_path,
            self.task.filepath,
            '--background',
            '--python-expr', self.generate_command()
        ], stdout=subprocess.PIPE)

        # Read render output
        for line in self.proc.stdout:
            if self._stop_event.isSet(): break

            # Get frame number
            match = frame_re.match(line.decode('utf-8'))
            if match:
                with self._lock:
                    self._frame = int(match.string[
                        match.regs[1][0]:match.regs[1][1]
                    ])

        # Handle backup
        if self._stop_event.isSet():
            # Remove files
            for file_name in listdir(self.task.output):
                file_path = path.join(self.task.output, file_name)
                if path.isfile(file_path):
                    remove_file(file_path)

            # Restore backup
            for file_name in listdir(backup_path):
                move_file(
                    path.join(backup_path, file_name),
                    path.join(self.task.output, file_name)
                )

        # Remove backup folder
        rmtree(backup_path)

        # Terminate process
        self.proc.terminate()
        self.proc.wait()

    # Generate render command
    def generate_command(self):
        return ";".join((
            'import bpy',
            'scene = bpy.data.scenes[%s]',
            'camera_name = %s',
            'scene.camera = bpy.data.objects[camera_name] '\
                'if camera_name != "" else scene.camera',
            'scene.frame_start = %i',
            'scene.frame_end = %i',
            'scene.render.use_sequencer = %s',
            'scene.render.filepath = %s',
            'scene.render.use_overwrite = True',
            'scene.render.use_file_extension = True',
            'scene.render.use_render_cache = False',
            'scene.render.use_placeholder = False',
            'bpy.ops.render.render(animation=True, scene=scene.name)'
        )) % (
            json.dumps(self.task.scene_name),
            json.dumps(self.task.camera_name),
            self.task.frame_start,
            self.task.frame_end,
            str(self.task.use_sequence),
            json.dumps(self.task.output)
        )

    # Get frame count
    def get_frame_count(self):
        return self.task.frame_end - self.task.frame_start + 1

    # Get rendered frame count
    def get_render_count(self):
        with self._lock:
            return self._frame - self.task.frame_start + 1

    # Stop rendering
    def stop(self):
        self._stop_event.set()

# Render scene strip operator
class RenderSceneStripOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.render_scene_strip"
    bl_label = "Render Scene Strip"
    bl_description = "Render scene strip in the background"
    bl_options = {'REGISTER'}

    # Show only for scene strips
    @classmethod
    def poll(cls, context):
        return (
            context.space_data.type == 'SEQUENCE_EDITOR' \
            and context.scene.sequence_editor is not None \
            and context.scene.sequence_editor.active_strip is not None \
            and context.scene.sequence_editor.active_strip.type == 'SCENE' \
            and context.scene.sequence_editor.active_strip.scene is not None
        )

    # Start rendering
    def execute(self, context):
        # Store UI region
        self.ui_area = context.area

        # Get filepath
        self.filepath = path.join(bpy.app.tempdir, RENDER_FILE_NAME)
        counter = 0
        while path.exists(self.filepath + str(counter)):
            counter += 1
        self.filepath += str(counter)

        # Get sequences with active first
        active_strip = context.scene.sequence_editor.active_strip
        render_sequences = [active_strip] + [
            strip for strip in (context.selected_sequences or []) \
                if strip != active_strip and strip.type == 'SCENE'
        ]

        # Get scene names
        tasks = []
        for strip in render_sequences:
            if strip.scene is not None:
                camera = strip.scene_camera or strip.scene.camera
                if strip.use_sequence or strip.scene.render.use_compositing \
                or camera is not None:
                    # Create render task
                    tasks.append(RenderTask(self.filepath, strip))

        # Abort if no renderable strips
        if len(tasks) == 0:
            self.report({'ERROR'}, "No renderable strips selected")
            return {'CANCELLED'}

        # Save render file
        bpy.ops.wm.save_as_mainfile(
            filepath=self.filepath, relative_remap=True, copy=True
        )

        # Create render task threads
        self.render_threads = []
        for task in tasks:
            self.render_threads.append(RenderThread(task))

        # Start threads
        for thread in self.render_threads:
            thread.start()

        # Set up modal execution
        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(
            0.1, context.window
        )
        return {'RUNNING_MODAL'}

    # Handle event
    def modal(self, context, event):
        if event.type == 'TIMER':
            # Update scenes
            for thread in self.render_threads:
                # Update render progress
                thread.task.strip.sf_scene_props.render_progress = int(
                    100.0 * thread.get_render_count() / thread.get_frame_count()
                )

                # Abort if requested
                if thread.task.strip.sf_scene_props.abort_render:
                    thread.task.strip.sf_scene_props.abort_render = False
                    thread.task.strip.sf_scene_props.render_progress = -1
                    thread.stop()

                # Handel dead threads
                if not thread.is_alive():
                    thread.task.strip.sf_scene_props.render_progress = -1
                    self.render_threads.remove(thread)

            # Redraw region
            self.ui_area.tag_redraw()

            # Finish if all threads dead
            if len(self.render_threads) == 0:
                self.cancel(context)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    # Abort rendering
    def cancel(self, context):
        # Stop threads
        for thread in self.render_threads:
            thread.task.strip.sf_scene_props.render_progress = -1
            thread.stop()

        # Delete render file
        remove_file(self.filepath)

        # Remove timer
        context.window_manager.event_timer_remove(self._timer)
        self._timer = None
        return {'CANCELLED'}

# Abort scene render operator
class AbortSceneRenderOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.abort_scene_render"
    bl_label = "Abort Scene Rendering"
    bl_description = "Abort Scene Rendering"
    bl_options = {'REGISTER'}

    # Show only for rendering scene strips
    @classmethod
    def poll(cls, context):
        if context.space_data.type != 'SEQUENCE_EDITOR': return False
        if context.scene.sequence_editor is None: return False
        active_strip = context.scene.sequence_editor.active_strip
        return (active_strip is not None and active_strip.type == 'SCENE' \
            and active_strip.sf_scene_props.render_progress != -1
        )

    # Request render abortion
    def execute(self, context):
        active_strip = context.scene.sequence_editor.active_strip

        # Set abort flag
        active_strip.sf_scene_props.abort_render = True

        return {'FINISHED'}

# Switch to rendered strip operator
class SwitchToRenderedStripOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.switch_to_rendered_strip"
    bl_label = "Switch to rendered strip"
    bl_description = "Replace scene strip with rendered image strip"
    bl_options = {'REGISTER', 'UNDO'}

    # Show only for scene strips
    @classmethod
    def poll(cls, context):
        if context.space_data.type != 'SEQUENCE_EDITOR': return False
        if context.scene.sequence_editor is None: return False
        active_strip = context.scene.sequence_editor.active_strip
        if active_strip is None or active_strip.type != 'SCENE': return False
        if active_strip.sf_scene_props.render_progress != -1: return False
        if active_strip.sf_scene_props.id == "": return False
        return True

    # Render scene strip
    def invoke(self, context, event):


        return {'FINISHED'}

# Clean scene renders operator
class CleanSceneRendersOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.clean_scene_renders"
    bl_label = "Clean Scene Renders"
    bl_description = "Remove unreferenced scene renders"
    bl_options = {'REGISTER', 'UNDO'}

    # Show only in sequence editor
    @classmethod
    def poll(cls, context):
        return (context.space_data.type == 'SEQUENCE_EDITOR')

    # Remove renders
    def execute(self, context):
        render_path = bpy.path.abspath(RENDER_DIR)

        # Get strip ids
        strip_ids = set()
        for scene in bpy.data.scenes:
            if scene.sequence_editor is not None:
                for strip in scene.sequence_editor.sequences_all:
                    if asattr(strip, 'sf_scene_props') \
                    and strip.sf_scene_props.id != "":
                        strip_ids.add(strip.sf_scene_props.id)

        # Remove unreferenced folders
        file_list = listdir(render_path)
        for file_name in file_list:
            file_path = path.join(render_path, file_name)
            if path.isdir(file_path):
                if file_name not in strip_ids:
                    rmtree(file_path)

        return {'FINISHED'}

# Remove scene operator
class RemoveSceneOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.remove_scene_strip"
    bl_label = "Remove Scene"
    bl_description = "Remove scene and sequencer strip"

    # Show only for scene strips
    @classmethod
    def poll(cls, context):
        if context.scene.sequence_editor is None: return False
        strip = context.scene.sequence_editor.active_strip
        return (
            strip is not None \
            and strip.type == 'SCENE' \
            and strip.scene is not None
        )

    # Show confirmation dialog
    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    # Remove scene and strip
    def execute(self, context):
        strip = context.scene.sequence_editor.active_strip

        # Remove scene
        bpy.data.scenes.remove(strip.scene, do_unlink=True)

        # Remove strip (taking groups into account)
        selected = context.selected_sequences
        for seq in selected:
            seq.select = False
        strip.select = True
        bpy.ops.sequencer.delete()
        for seq in selected:
            seq.select = True

        return {'FINISHED'}

# Scene tools Panel
class SceneToolsPanel(bpy.types.Panel):
    # Meta data
    bl_label = "Scene Tools"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"

    # Show only for text scenes
    @classmethod
    def poll(cls, context):
        return (
            context.space_data.type == 'SEQUENCE_EDITOR' \
            and context.scene.sequence_editor is not None \
            and context.scene.sequence_editor.active_strip is not None \
            and context.scene.sequence_editor.active_strip.type == 'SCENE' \
            and context.scene.sequence_editor.active_strip.scene is not None
        )

    # Draw panel
    def draw(self, context):
        # Get strips
        active_strip = context.scene.sequence_editor.active_strip

        # Get sequences with active first
        active_strip = context.scene.sequence_editor.active_strip
        scene_strips = [active_strip] + [
            strip for strip in (context.selected_sequences or []) \
                if strip != active_strip and strip.type == 'SCENE'
        ]

        # Edit scene
        edit_row = self.layout.row()
        edit_row.operator(EditSceneOperator.bl_idname)
        edit_row.prop(
            active_strip.scene.sf_scene_props, 'edit_screen', text="",
            icon='SPLITSCREEN'
        )

        # Resolution percentage
        self.layout.prop(active_strip.scene.render, 'resolution_percentage')

        # Render
        if active_strip.sf_scene_props.render_progress == -1:
            # Render scene
            self.layout.operator(
                RenderSceneStripOperator.bl_idname, icon='RENDER_STILL',
                text="Render strip" if len(scene_strips) == 1 else \
                "Render strips"
            )
        else:
            # Render progress row
            progress_row = self.layout.row()
            progress_row.prop(
                active_strip.sf_scene_props, 'render_display'
            )
            progress_row.operator(
                AbortSceneRenderOperator.bl_idname, text="", icon='X'
            )

        # Switch to rendered strip
        self.layout.operator(SwitchToRenderedStripOperator.bl_idname)

        # Clean scene renders
        self.layout.operator(CleanSceneRendersOperator.bl_idname)

        # Remove scene
        self.layout.operator(RemoveSceneOperator.bl_idname, icon='X')

### Rendered strip panel ###
############################

# Switch to scene strip operator
class SwitchToSceneStripOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.switch_to_scene_strip"
    bl_label = "Switch to scene strip"
    bl_description = "Replace rendered image strip with scene strip"
    bl_options = {'REGISTER', 'UNDO'}

    # Show only for scene strips
    @classmethod
    def poll(cls, context):
        return (
            context.space_data.type == 'SEQUENCE_EDITOR' \
            and context.scene.sequence_editor is not None \
            and context.scene.sequence_editor.active_strip is not None \
            and (
                context.scene.sequence_editor.active_strip.type == 'IMAGE' or \
                context.scene.sequence_editor.active_strip.type == 'MOVIE'
            )
        )

    # Render scene strip
    def invoke(self, context, event):
        return {'FINISHED'}

# Rendered strip panel
class RenderedStripPanel(bpy.types.Panel):
    # Meta data
    bl_label = "Rendered Strip Tools"
    bl_space_type = "SEQUENCE_EDITOR"
    bl_region_type = "UI"

    # Show only for text scenes
    @classmethod
    def poll(cls, context):
        return SwitchToSceneStripOperator.poll(context)

    # Draw panel
    def draw(self, context):
        # Get strips
        selected_scene_strips = list(filter(
            lambda s: s.type == 'SCENE', context.selected_sequences
        ))

        # Switch to scene strip
        self.layout.operator(SwitchToSceneStripOperator.bl_idname)

### Back to sequencer ###
#########################

# Back to sequencer operator
class BackToSequencerOperator(bpy.types.Operator):
    # Meta data
    bl_idname = "sf_addons.back_to_sequencer"
    bl_label = "Back to Sequencer"
    bl_description = "Switch back to sequence editing"

    # Show only if vse scene defined
    @classmethod
    def poll(cls, context):
        return (
            context.scene.sf_scene_props.vse_scene_id != "" \
            and get_scene(context.scene.sf_scene_props.vse_scene_id) is not None
        )

    # Back to sequencer
    def invoke(self, context, event):
        # Get scene properties
        scene_props = context.scene.sf_scene_props

        # Switch screen
        switch_screen(context, scene_props.vse_screen)

        # Switch scene
        context.screen.scene = get_scene(scene_props.vse_scene_id)

        return {'FINISHED'}

# Back to sequencer button
def back_to_sequencer_button(self, context):
    if BackToSequencerOperator.poll(context):
        self.layout.operator(
            BackToSequencerOperator.bl_idname, icon='SEQ_SEQUENCER'
        )

### Module registration ###
###########################AA

# Register module
def register():
    # Register module
    bpy.utils.register_module(__name__)

    # Register scene properties
    bpy.types.Scene.sf_scene_props = bpy.props.PointerProperty(
        type=SceneProperties
    )

    # Register strip properties
    bpy.types.SceneSequence.sf_scene_props = \
    bpy.types.ImageSequence.sf_scene_props = \
    bpy.types.MovieSequence.sf_scene_props = bpy.props.PointerProperty(
        type=StripProperties
    )

    # Add render percentage button
    bpy.types.RENDER_PT_dimensions.append(distribute_button)

    # Add back to sequencer button
    bpy.types.INFO_HT_header.append(back_to_sequencer_button)

    # Add keyboard shortcut
    kmis = bpy.context.window_manager.keyconfigs.default\
        .keymaps['Sequencer'].keymap_items
    kmis.new(EditSceneOperator.bl_idname, 'TAB', 'PRESS', head=True)

# Unregister module
def unregister():
    # Unregister module
    bpy.utils.unregister_module(__name__)

    # Unregister scene properties
    del bpy.types.Scene.sf_scene_props

    # Remove render percentage button
    bpy.types.RENDER_PT_dimensions.remove(distribute_button)

    # Remove back to sequencer button
    bpy.types.INFO_HT_header.remove(back_to_sequencer_button)

    # Remove keyboard shortcut
    kmis = bpy.context.window_manager.keyconfigs.default\
        .keymaps['Sequencer'].keymap_items
    for item in kmis:
        if item.idname == EditSceneOperator.bl_idname:
            kmis.remove(item)

# Register if executed as script
if __name__ == '__main__':
    register()
