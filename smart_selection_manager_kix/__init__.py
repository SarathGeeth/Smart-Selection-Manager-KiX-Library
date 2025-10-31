bl_info = {
    "name": "Smart Selection Manager - KiX Library By REX",
    "author": "SarathGeeth, rexrohar",
    "version": (0, 1, 1),
    "blender": (4, 5, 0),
    "location": "3D View > Sidebar > Smart Selection - KIX",
    "description": "Save and manage selections with show-all toggle, quick-restore popup, safe restore, and smart mode-based filtering. Ctrl+Click restore + multi-select support.",
    "category": "Selection",
}

import bpy
import bmesh
from bpy.props import StringProperty, EnumProperty, IntProperty, CollectionProperty, BoolProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList

class SSItem(PropertyGroup):
    name: StringProperty(name="Name")
    group: StringProperty(name="Group", default="Default")
    mode: EnumProperty(
        name="Mode",
        items=[
            ('OBJECT', 'Object', 'Object mode selection'),
            ('VERT', 'Vertices', 'Vertex selection'),
            ('EDGE', 'Edges', 'Edge selection'),
            ('FACE', 'Faces', 'Face selection'),
        ],
    )
    object_name: StringProperty(name="Object")
    data: StringProperty(name="Data")
    is_multi_selected: BoolProperty(name="Multi Selected", default=False)

def get_selected_objects_names(context):
    return [o.name for o in context.selected_objects]

def get_edit_selection_indices(context):
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return None
    mesh = obj.data
    bm = bmesh.from_edit_mesh(mesh)
    if any(f.select for f in bm.faces):
        sel_type = 'FACE'
        idxs = [str(f.index) for f in bm.faces if f.select]
    elif any(e.select for e in bm.edges):
        sel_type = 'EDGE'
        idxs = [str(e.index) for e in bm.edges if e.select]
    else:
        sel_type = 'VERT'
        idxs = [str(v.index) for v in bm.verts if v.select]
    return sel_type, obj.name, idxs

def ensure_index_in_range(scn):
    if not scn.ss_items:
        scn.ss_index = -1
    else:
        scn.ss_index = max(0, min(scn.ss_index, len(scn.ss_items) - 1))

def get_multi_selected_indices(scn):
    return [i for i, it in enumerate(scn.ss_items) if getattr(it, "is_multi_selected", False)]

class SS_OT_add(Operator):
    bl_idname = "ss.add_selection"
    bl_label = "Add Selection"
    bl_options = {'REGISTER', 'UNDO'}
    name: StringProperty(name="Name", default="Selection")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        scn = context.scene
        mode = context.mode
        item = scn.ss_items.add()
        item.name = self.name
        if mode == 'OBJECT':
            item.mode = 'OBJECT'
            item.data = ','.join(get_selected_objects_names(context))
        elif mode.startswith('EDIT'):
            res = get_edit_selection_indices(context)
            if not res:
                self.report({'ERROR'}, 'Active object is not a mesh in Edit Mode')
                scn.ss_items.remove(len(scn.ss_items) - 1)
                return {'CANCELLED'}
            sel_type, obj_name, idxs = res
            item.mode = sel_type
            item.object_name = obj_name
            item.data = ','.join(idxs)
        else:
            scn.ss_items.remove(len(scn.ss_items) - 1)
            self.report({'ERROR'}, 'Unsupported mode')
            return {'CANCELLED'}
        scn.ss_index = len(scn.ss_items) - 1
        self.report({'INFO'}, f"Saved '{item.name}'")
        return {'FINISHED'}

class SS_OT_toggle_update(Operator):
    bl_idname = "ss.toggle_update_selection"
    bl_label = "Update or Remove Selection"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()
    remove_mode: BoolProperty(default=False)

    def execute(self, context):
        scn = context.scene
        if self.index < 0 or self.index >= len(scn.ss_items):
            return {'CANCELLED'}
        item = scn.ss_items[self.index]
        mode = context.mode
        if mode == 'OBJECT':
            selected = set(get_selected_objects_names(context))
            current = set(item.data.split(',')) if item.data else set()
            if self.remove_mode:
                current -= selected
                msg = "Removed selected objects"
            else:
                current |= selected
                msg = "Added selected objects"
            item.data = ','.join(current)
        elif mode.startswith('EDIT'):
            res = get_edit_selection_indices(context)
            if not res:
                self.report({'ERROR'}, 'Active object is not a mesh in Edit Mode')
                return {'CANCELLED'}
            sel_type, obj_name, idxs = res
            if item.object_name != obj_name:
                self.report({'ERROR'}, 'Different mesh object selected')
                return {'CANCELLED'}
            selected = set(idxs)
            current = set(item.data.split(',')) if item.data else set()
            if self.remove_mode:
                current -= selected
                msg = "Removed selected elements"
            else:
                current |= selected
                msg = "Added selected elements"
            item.data = ','.join(current)
            item.mode = sel_type
            item.object_name = obj_name
        else:
            self.report({'ERROR'}, 'Unsupported mode')
            return {'CANCELLED'}
        self.report({'INFO'}, f"{msg} in '{item.name}'")
        return {'FINISHED'}

class SS_OT_restore(Operator):
    bl_idname = "ss.restore_selection"
    bl_label = "Restore Selection"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty(default=-1)

    def execute(self, context):
        scn = context.scene
        multi_idxs = get_multi_selected_indices(scn)
        if multi_idxs:
            merged_object_names = set()
            merged_edit_info = {}
            for i in multi_idxs:
                if i < 0 or i >= len(scn.ss_items):
                    continue
                it = scn.ss_items[i]
                data_items = [d for d in (it.data or "").split(',') if d]
                if it.mode == 'OBJECT' or not all(di.isdigit() for di in data_items):
                    for name in data_items:
                        merged_object_names.add(name)
                else:
                    objname = it.object_name
                    key = (objname, it.mode)
                    s = merged_edit_info.get(key, set())
                    for di in data_items:
                        if di.isdigit():
                            s.add(int(di))
                    merged_edit_info[key] = s
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
            bpy.ops.object.select_all(action='DESELECT')
            for name in merged_object_names:
                obj = bpy.data.objects.get(name)
                if obj:
                    obj.select_set(True)
            for (objname, mode_key), ids in merged_edit_info.items():
                obj = bpy.data.objects.get(objname)
                if not obj:
                    continue
                obj.select_set(True)
                context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='EDIT')
                mesh = obj.data
                bm = bmesh.from_edit_mesh(mesh)
                for v in bm.verts:
                    v.select = False
                for e in bm.edges:
                    e.select = False
                for f in bm.faces:
                    f.select = False
                bm.verts.ensure_lookup_table()
                bm.edges.ensure_lookup_table()
                bm.faces.ensure_lookup_table()
                seq = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[mode_key]
                for i in ids:
                    if i < len(seq):
                        seq[i].select = True
                bmesh.update_edit_mesh(mesh, loop_triangles=True)
                bpy.ops.object.mode_set(mode='OBJECT')
            if merged_object_names:
                first = next(iter(merged_object_names))
                if first in bpy.data.objects:
                    context.view_layer.objects.active = bpy.data.objects[first]
            return {'FINISHED'}
        idx = self.index if self.index >= 0 else scn.ss_index
        if idx < 0 or idx >= len(scn.ss_items):
            return {'CANCELLED'}
        item = scn.ss_items[idx]
        prev_mode = context.mode
        data_items = [i for i in item.data.split(',') if i]
        is_numeric = all(i.isdigit() for i in data_items)
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
        bpy.ops.object.select_all(action='DESELECT')
        if item.mode == 'OBJECT' or not is_numeric:
            for name in data_items:
                obj = bpy.data.objects.get(name)
                if obj:
                    obj.select_set(True)
            if data_items:
                first = data_items[0]
                if first and first in bpy.data.objects:
                    context.view_layer.objects.active = bpy.data.objects[first]
            if prev_mode.startswith('EDIT'):
                bpy.ops.object.mode_set(mode='EDIT')
            return {'FINISHED'}
        obj = bpy.data.objects.get(item.object_name)
        if not obj:
            self.report({'WARNING'}, f"Object '{item.object_name}' not found")
            return {'CANCELLED'}
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        for v in bm.verts:
            v.select = False
        for e in bm.edges:
            e.select = False
        for f in bm.faces:
            f.select = False
        ids = [int(i) for i in data_items if i.isdigit()]
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        seq = {"VERT": bm.verts, "EDGE": bm.edges, "FACE": bm.faces}[item.mode]
        for i in ids:
            if i < len(seq):
                seq[i].select = True
        bmesh.update_edit_mesh(mesh, loop_triangles=True)
        if prev_mode == 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}

class SS_OT_delete(Operator):
    bl_idname = "ss.delete_selection"
    bl_label = "Delete Selection"
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()
    def execute(self, context):
        scn = context.scene
        if 0 <= self.index < len(scn.ss_items):
            scn.ss_items.remove(self.index)
            ensure_index_in_range(scn)
        return {'FINISHED'}

class SS_OT_list_click(Operator):
    bl_idname = "ss.list_click"
    bl_label = "List Item Click"
    bl_options = {'INTERNAL'}
    index: IntProperty(default=-1)
    def invoke(self, context, event):
        scn = context.scene
        idx = int(self.index)
        if event.ctrl and not event.shift:
            scn.ss_index = idx
            for it in scn.ss_items:
                it.is_multi_selected = False
            bpy.ops.ss.restore_selection(index=idx)
            scn.ss_last_click = idx
            return {'FINISHED'}
        if event.shift and not event.ctrl:
            last = getattr(scn, "ss_last_click", -1)
            if last < 0 or last >= len(scn.ss_items):
                for i, it in enumerate(scn.ss_items):
                    it.is_multi_selected = (i == idx)
            else:
                start = min(last, idx)
                end = max(last, idx)
                for i, it in enumerate(scn.ss_items):
                    it.is_multi_selected = (start <= i <= end)
            scn.ss_index = idx
            scn.ss_last_click = idx
            return {'FINISHED'}
        if event.ctrl and event.shift:
            it = scn.ss_items[idx]
            it.is_multi_selected = not it.is_multi_selected
            scn.ss_index = idx
            scn.ss_last_click = idx
            return {'FINISHED'}
        for i, it in enumerate(scn.ss_items):
            it.is_multi_selected = (i == idx)
        scn.ss_index = idx
        scn.ss_last_click = idx
        return {'FINISHED'}

class SS_OT_quick_restore(Operator):
    bl_idname = "ss.open_quick_restore"
    bl_label = "Quick Restore Popup"
    bl_options = {'REGISTER'}
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)
    def draw(self, context):
        SS_PT_panel.draw(self, context)
    def execute(self, context):
        return {'FINISHED'}

class SS_UIList(UIList):
    def filter_items(self, context, data, propname):
        scn = context.scene
        items = getattr(data, propname)
        flt_flags = []
        flt_neworder = []
        current_mode = context.mode
        active_obj = context.active_object.name if context.active_object else ""
        for item in items:
            if scn.ss_show_all:
                flt_flags.append(self.bitflag_filter_item)
            elif current_mode == 'OBJECT' and item.mode == 'OBJECT':
                flt_flags.append(self.bitflag_filter_item)
            elif current_mode.startswith('EDIT') and item.object_name == active_obj:
                flt_flags.append(self.bitflag_filter_item)
            else:
                flt_flags.append(0)
        return flt_flags, flt_neworder

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        icon_map = {'OBJECT': 'OBJECT_DATAMODE', 'VERT': 'VERTEXSEL', 'EDGE': 'EDGESEL', 'FACE': 'FACESEL'}
        row = layout.row(align=True)
        row.label(icon=icon_map.get(item.mode, 'QUESTION'))
        label_text = item.name
        if getattr(item, "is_multi_selected", False):
            label_text = "✓ " + label_text
        click = row.operator('ss.list_click', text=label_text, emboss=False)
        click.index = index
        sub = row.row(align=True)
        sub.operator('ss.restore_selection', text='', icon='FILE_TICK').index = index
        sub.operator('ss.delete_selection', text='', icon='TRASH').index = index

class SS_PT_panel(Panel):
    bl_label = "Smart Selection - KIX"
    bl_idname = "VIEW3D_PT_save_selection"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Smart Selection - KIX'
    def draw(self, context):
        scn = context.scene
        layout = self.layout
        current_mode = context.mode
        layout.label(text=f"Mode: {current_mode}")
        layout.prop(scn, "ss_show_all", text="Show All Lists")
        row = layout.row()
        row.template_list("SS_UIList", "", scn, "ss_items", scn, "ss_index", rows=6, maxrows=12)
        layout.separator()
        row = layout.row(align=True)
        row.operator('ss.add_selection', text='Add Selection', icon='ADD')
        idx = scn.ss_index
        if 0 <= idx < len(scn.ss_items):
            item = scn.ss_items[idx]
            mode = context.mode
            remove_mode = False
            can_act = False
            label = "Update Selection"
            if mode == 'OBJECT':
                selected = {o.name for o in context.selected_objects}
                saved = set(item.data.split(',')) if item.mode == 'OBJECT' else set()
                if selected:
                    if selected & saved:
                        label, remove_mode, can_act = "Remove Selected", True, True
                    else:
                        can_act = True
            elif mode.startswith('EDIT') and context.active_object and item.object_name == context.active_object.name:
                res = get_edit_selection_indices(context)
                if res:
                    _, _, idxs = res
                    selected = set(idxs)
                    saved = set(item.data.split(',')) if item.data else set()
                    if selected & saved:
                        label, remove_mode, can_act = "Remove Selected", True, True
                    else:
                        can_act = True
            sub = row.row(align=True)
            sub.enabled = can_act
            op = sub.operator('ss.toggle_update_selection', text=label, icon='FILE_REFRESH')
            op.index = idx
            op.remove_mode = remove_mode
        layout.separator()
        row = layout.row(align=True)
        row.operator('ss.restore_selection', text='Quick Restore Active', icon='FILE_TICK')
        if not isinstance(self, SS_OT_quick_restore):
            row.operator('ss.open_quick_restore', text='Open Popup (Ctrl+Shift+R)', icon='VIEWZOOM')

classes = (
    SSItem,
    SS_OT_add,
    SS_OT_toggle_update,
    SS_OT_restore,
    SS_OT_delete,
    SS_OT_list_click,
    SS_OT_quick_restore,
    SS_UIList,
    SS_PT_panel,
)

addon_keymaps = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ss_items = CollectionProperty(type=SSItem)
    bpy.types.Scene.ss_index = IntProperty(default=-1)
    bpy.types.Scene.ss_show_all = BoolProperty(name="Show All Lists", description="Show all saved selections, regardless of mode or object", default=False)
    bpy.types.Scene.ss_popup_index = IntProperty(default=0)
    bpy.types.Scene.ss_last_click = IntProperty(default=-1)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new('ss.open_quick_restore', 'R', 'PRESS', ctrl=True, shift=True)
        addon_keymaps.append((km, kmi))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    try:
        del bpy.types.Scene.ss_index
        del bpy.types.Scene.ss_items
        del bpy.types.Scene.ss_show_all
        del bpy.types.Scene.ss_popup_index
        del bpy.types.Scene.ss_last_click
    except Exception:
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == '__main__':
    register()
