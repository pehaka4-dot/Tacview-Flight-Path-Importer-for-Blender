
bl_info = {
    "name": "Tacview Flight Path Importer",
    "author": "Ryan",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Tacview",
    "description": "Import Tacview CSV flight data and recreate flight paths with animation",
    "category": "Import-Export",
}

import bpy
import csv
import math
from datetime import datetime
from mathutils import Vector, Euler, Quaternion
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    IntProperty,
    EnumProperty,
)
from bpy.types import Operator, Panel, PropertyGroup


# ---------------------------------------------------------------------------
#  Utility helpers
# ---------------------------------------------------------------------------

def parse_iso_time(iso_str):
    """Parse ISO 8601 timestamp string to datetime object."""
    iso_str = iso_str.strip()
    # Handle 'Z' suffix
    if iso_str.endswith('Z'):
        iso_str = iso_str[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(iso_str)
    except ValueError:
        # Fallback for formats without timezone
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
            try:
                return datetime.strptime(iso_str, fmt)
            except ValueError:
                continue
    return None


def geo_to_local(lon, lat, alt, origin):
    """
    Convert geographic coordinates to local metric coordinates.
    Origin is (lon0, lat0, alt0) – the first data point.
    Returns (x, y, z) in metres.
      X = East   (longitude difference)
      Y = North  (latitude difference)
      Z = Up     (altitude difference)
    """
    lon0, lat0, alt0 = origin
    lat0_rad = math.radians(lat0)
    x = (lon - lon0) * math.cos(lat0_rad) * 111320.0
    y = (lat - lat0) * 111320.0
    z = alt - alt0
    return (x, y, z)


def create_arrow_mesh(name, size=1.0):
    """
    Create a simple arrow mesh pointing along the +Y axis.
    The arrow shape makes flight direction clearly visible.
    """
    # Arrow body (elongated diamond) + tail fins
    s = size
    verts = [
        # Nose (front tip)
        (0, s * 3.0, 0),
        # Body sides
        (-s * 0.4, 0, 0),       # left
        (s * 0.4, 0, 0),        # right
        (0, 0, s * 0.3),        # top
        (0, 0, -s * 0.3),       # bottom
        # Tail
        (0, -s * 1.5, 0),
        # Tail fin tips
        (-s * 1.0, -s * 1.2, 0),   # left fin
        (s * 1.0, -s * 1.2, 0),    # right fin
        (0, -s * 1.2, s * 0.8),    # top fin
    ]

    faces = [
        # Nose cone
        (0, 1, 3),   # nose-left-top
        (0, 3, 2),   # nose-top-right
        (0, 2, 4),   # nose-right-bottom
        (0, 4, 1),   # nose-bottom-left
        # Body to tail
        (5, 3, 1),   # tail-top-left
        (5, 2, 3),   # tail-right-top
        (5, 4, 2),   # tail-bottom-right
        (5, 1, 4),   # tail-left-bottom
        # Left tail fin
        (6, 1, 5),
        # Right tail fin
        (7, 5, 2),
        # Top tail fin
        (8, 3, 5),
    ]

    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def parse_csv_data(filepath):
    """
    Parse a Tacview CSV file and return structured flight data.
    Returns a dict keyed by aircraft ID:
      { id: { 'name': str, 'points': [ {time, lon, lat, alt, roll, pitch, yaw}, ... ] } }
    """
    aircraft_data = {}

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                ac_id = row.get('Id', '').strip()
                if not ac_id:
                    continue

                iso_time = row.get('ISO time', '').strip()
                lon_str = row.get('Longitude', '').strip()
                lat_str = row.get('Latitude', '').strip()
                alt_str = row.get('Altitude', '').strip()
                roll_str = row.get('Roll', '').strip()
                pitch_str = row.get('Pitch', '').strip()
                yaw_str = row.get('Yaw', '').strip()

                # Skip rows with missing essential data
                if not all([iso_time, lon_str, lat_str, alt_str]):
                    continue

                dt = parse_iso_time(iso_time)
                if dt is None:
                    continue

                point = {
                    'time': dt,
                    'lon': float(lon_str),
                    'lat': float(lat_str),
                    'alt': float(alt_str),
                    'roll': float(roll_str) if roll_str else 0.0,
                    'pitch': float(pitch_str) if pitch_str else 0.0,
                    'yaw': float(yaw_str) if yaw_str else 0.0,
                }

                if ac_id not in aircraft_data:
                    ac_name = row.get('Name', '').strip() or f'Aircraft_{ac_id}'
                    aircraft_data[ac_id] = {
                        'name': ac_name,
                        'points': [],
                    }

                aircraft_data[ac_id]['points'].append(point)

            except (ValueError, KeyError):
                continue

    # Sort each aircraft's points by time
    for ac_id in aircraft_data:
        aircraft_data[ac_id]['points'].sort(key=lambda p: p['time'])

    return aircraft_data


# ---------------------------------------------------------------------------
#  Properties
# ---------------------------------------------------------------------------

class TacviewFlightPathProperties(PropertyGroup):
    csv_filepath: StringProperty(
        name="CSV File",
        description="Path to the Tacview CSV export file",
        subtype='FILE_PATH',
        default="",
    )

    use_scene_fps: BoolProperty(
        name="Use Scene FPS",
        description="Use the current scene frame rate. Uncheck to set a custom FPS",
        default=True,
    )

    custom_fps: FloatProperty(
        name="Custom FPS",
        description="Custom frames per second for animation",
        default=24.0,
        min=1.0,
        max=240.0,
    )

    create_path_curve: BoolProperty(
        name="Create Path Curve",
        description="Generate a 3D curve showing the flight path",
        default=True,
    )

    arrow_size: FloatProperty(
        name="Arrow Size",
        description="Size of the arrow mesh representing the aircraft (in metres)",
        default=50.0,
        min=1.0,
        max=1000.0,
    )


# ---------------------------------------------------------------------------
#  Operator
# ---------------------------------------------------------------------------

class TACVIEW_OT_ImportFlightPath(Operator):
    bl_idname = "tacview.import_flight_path"
    bl_label = "Import Flight Path"
    bl_description = "Import Tacview CSV and create animated flight path"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.tacview_props
        filepath = bpy.path.abspath(props.csv_filepath)

        if not filepath:
            self.report({'ERROR'}, "Please select a CSV file")
            return {'CANCELLED'}

        import os
        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"File not found: {filepath}")
            return {'CANCELLED'}

        # Determine FPS
        if props.use_scene_fps:
            fps = context.scene.render.fps / context.scene.render.fps_base
        else:
            fps = props.custom_fps

        # Parse CSV
        self.report({'INFO'}, "Parsing CSV file...")
        aircraft_data = parse_csv_data(filepath)

        if not aircraft_data:
            self.report({'ERROR'}, "No valid flight data found in CSV")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Found {len(aircraft_data)} aircraft(s)")

        # Determine global origin from the very first data point (across all aircraft)
        all_first_points = []
        for ac_id, data in aircraft_data.items():
            if data['points']:
                all_first_points.append(data['points'][0])

        if not all_first_points:
            self.report({'ERROR'}, "No data points found")
            return {'CANCELLED'}

        # Use earliest point as origin
        all_first_points.sort(key=lambda p: p['time'])
        origin_point = all_first_points[0]
        origin = (origin_point['lon'], origin_point['lat'], origin_point['alt'])
        time_origin = origin_point['time']

        # Create a collection for the flight paths
        collection_name = "Tacview Flight Paths"
        if collection_name in bpy.data.collections:
            flight_collection = bpy.data.collections[collection_name]
        else:
            flight_collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(flight_collection)

        max_frame = 1

        # Process each aircraft
        for ac_id, data in aircraft_data.items():
            points = data['points']
            ac_name = data['name']

            if len(points) < 2:
                continue

            # --- Create arrow mesh object ---
            mesh = create_arrow_mesh(f"{ac_name}_{ac_id}", size=props.arrow_size)
            obj = bpy.data.objects.new(f"{ac_name}_{ac_id}", mesh)
            flight_collection.objects.link(obj)

            # Assign a random color material
            mat = bpy.data.materials.new(name=f"{ac_name}_{ac_id}_Mat")
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                # Generate a distinct colour per aircraft based on ID hash
                hue = (hash(ac_id) % 360) / 360.0
                import colorsys
                r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
                bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)
                bsdf.inputs['Roughness'].default_value = 0.4
            obj.data.materials.append(mat)

            # --- Use QUATERNION rotation for smooth interpolation ---
            obj.rotation_mode = 'QUATERNION'

            # --- Create keyframes ---
            path_points = []  # for curve

            for point in points:
                # Calculate frame number
                dt_seconds = (point['time'] - time_origin).total_seconds()
                frame = int(round(dt_seconds * fps)) + 1

                if frame > max_frame:
                    max_frame = frame

                # Convert position
                x, y, z = geo_to_local(
                    point['lon'], point['lat'], point['alt'], origin
                )
                obj.location = (x, y, z)
                obj.keyframe_insert(data_path="location", frame=frame)

                path_points.append(Vector((x, y, z)))

                # Convert attitude (degrees to radians)
                # Tacview: Roll = bank angle, Pitch = nose up/down, Yaw = heading
                # Convert Euler → Quaternion for smooth interpolation
                # (avoids gimbal lock and rotation discontinuities)
                pitch_rad = math.radians(point['pitch'])
                roll_rad = math.radians(point['roll'])
                yaw_rad = math.radians(-point['yaw'])  # negate for right-hand convention

                euler = Euler((pitch_rad, roll_rad, yaw_rad), 'XYZ')
                obj.rotation_quaternion = euler.to_quaternion()
                obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)

            # Set interpolation to BEZIER with auto handles for smooth flight
            if obj.animation_data and obj.animation_data.action:
                for fcurve in obj.animation_data.action.fcurves:
                    for keyframe in fcurve.keyframe_points:
                        keyframe.interpolation = 'BEZIER'
                        keyframe.handle_left_type = 'AUTO_CLAMPED'
                        keyframe.handle_right_type = 'AUTO_CLAMPED'

            # --- Create path curve (optional) ---
            if props.create_path_curve and len(path_points) >= 2:
                curve_data = bpy.data.curves.new(
                    name=f"{ac_name}_{ac_id}_Path", type='CURVE'
                )
                curve_data.dimensions = '3D'
                curve_data.resolution_u = 12
                curve_data.bevel_depth = props.arrow_size * 0.05  # thin tube

                spline = curve_data.splines.new('NURBS')
                spline.points.add(len(path_points) - 1)
                spline.use_endpoint_u = True
                spline.order_u = 4  # cubic NURBS for smooth curves

                for i, pt in enumerate(path_points):
                    spline.points[i].co = (pt.x, pt.y, pt.z, 1.0)

                curve_obj = bpy.data.objects.new(
                    f"{ac_name}_{ac_id}_Path", curve_data
                )
                flight_collection.objects.link(curve_obj)

                # Path material (same hue but translucent)
                path_mat = bpy.data.materials.new(
                    name=f"{ac_name}_{ac_id}_PathMat"
                )
                path_mat.use_nodes = True
                path_bsdf = path_mat.node_tree.nodes.get("Principled BSDF")
                if path_bsdf:
                    hue = (hash(ac_id) % 360) / 360.0
                    import colorsys
                    r, g, b = colorsys.hsv_to_rgb(hue, 0.5, 0.7)
                    path_bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)
                    path_bsdf.inputs['Alpha'].default_value = 0.5
                path_mat.blend_method = 'BLEND' if hasattr(path_mat, 'blend_method') else None
                curve_obj.data.materials.append(path_mat)

            self.report({'INFO'}, f"  Aircraft '{ac_name}' (ID:{ac_id}): {len(points)} frames")

        # Update scene frame range
        context.scene.frame_start = 1
        context.scene.frame_end = max_frame
        context.scene.frame_set(1)

        self.report(
            {'INFO'},
            f"Imported {len(aircraft_data)} aircraft(s). "
            f"Animation range: 1 - {max_frame} frames"
        )
        return {'FINISHED'}


# ---------------------------------------------------------------------------
#  Panel
# ---------------------------------------------------------------------------

class TACVIEW_PT_FlightPathPanel(Panel):
    bl_label = "Tacview Flight Path"
    bl_idname = "TACVIEW_PT_flight_path"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tacview'

    def draw(self, context):
        layout = self.layout
        props = context.scene.tacview_props

        # File selection
        box = layout.box()
        box.label(text="CSV File", icon='FILE')
        box.prop(props, "csv_filepath", text="")

        # Settings
        box = layout.box()
        box.label(text="Settings", icon='PREFERENCES')

        row = box.row()
        row.prop(props, "use_scene_fps")
        if not props.use_scene_fps:
            row = box.row()
            row.prop(props, "custom_fps")
        else:
            fps = context.scene.render.fps / context.scene.render.fps_base
            row = box.row()
            row.label(text=f"Scene FPS: {fps:.1f}")

        box.prop(props, "arrow_size")
        box.prop(props, "create_path_curve")

        # Import button
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("tacview.import_flight_path", icon='IMPORT')


# ---------------------------------------------------------------------------
#  Registration
# ---------------------------------------------------------------------------

classes = (
    TacviewFlightPathProperties,
    TACVIEW_OT_ImportFlightPath,
    TACVIEW_PT_FlightPathPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.tacview_props = bpy.props.PointerProperty(
        type=TacviewFlightPathProperties
    )


def unregister():
    del bpy.types.Scene.tacview_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
