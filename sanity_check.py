"""
Sanity Check system for USD Exporter
Validates scene state before export
"""

import maya.cmds as cmds
import os
from datetime import datetime, timedelta

try:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
except ImportError:
    from PySide6.QtCore import *
    from PySide6.QtGui import *
    from PySide6.QtWidgets import *


class SanityCheckStatus:
    """Status types for sanity checks"""
    PASS = "pass"      # Green - check passed
    FAIL = "fail"      # Red - check failed (blocks export)
    IGNORED = "ignored"  # Black - check ignored by user
    WARNING = "warning"  # Orange - warning but doesn't block


class SanityCheck:
    """Base class for individual sanity checks"""
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.status = SanityCheckStatus.PASS
        self.message = ""
        self.details = []  # List of detailed error strings for reporting
        self.can_ignore = True  # Can this check be ignored by user?
        self.can_fix = False    # Can this check be auto-fixed?
    
    def run(self):
        """
        Run the check and return status
        Returns: (status, message) tuple
        """
        raise NotImplementedError("Subclasses must implement run()")
    
    def fix(self):
        """
        Attempt to fix the issue
        Returns: True if fixed successfully, False otherwise
        """
        return False
    
    def ignore(self):
        """Mark this check as ignored"""
        if self.can_ignore:
            self.status = SanityCheckStatus.IGNORED
    
    def reset(self):
        """Reset check to run again"""
        if self.status == SanityCheckStatus.IGNORED:
            self.status = SanityCheckStatus.PASS


class SceneSavedCheck(SanityCheck):
    """Check if scene has been saved recently"""
    
    def __init__(self, time_threshold_minutes=15):
        super(SceneSavedCheck, self).__init__(
            "Scene Saved",
            "Scene must be saved within last {} minutes".format(time_threshold_minutes)
        )
        self.time_threshold_minutes = time_threshold_minutes
        self.can_fix = True
    
    def run(self):
        """Check if scene was saved recently"""
        # Check if scene file exists
        scene_path = cmds.file(query=True, sceneName=True)
        
        if not scene_path:
            self.status = SanityCheckStatus.FAIL
            self.message = "Scene not saved"
            return self.status, self.message
        
        # Check if scene is modified
        is_modified = cmds.file(query=True, modified=True)
        
        if is_modified:
            self.status = SanityCheckStatus.FAIL
            self.message = "Scene has unsaved changes"
            return self.status, self.message
        
        # Check file modification time
        if os.path.exists(scene_path):
            file_time = datetime.fromtimestamp(os.path.getmtime(scene_path))
            current_time = datetime.now()
            time_diff = current_time - file_time
            
            if time_diff > timedelta(minutes=self.time_threshold_minutes):
                self.status = SanityCheckStatus.FAIL
                minutes_ago = int(time_diff.total_seconds() / 60)
                self.message = "Saved {} min ago (limit: {} min)".format(
                    minutes_ago, self.time_threshold_minutes
                )
                return self.status, self.message
        
        # All checks passed
        self.status = SanityCheckStatus.PASS
        self.message = "Scene saved recently"
        return self.status, self.message
    
    def fix(self):
        """Save the scene (Ctrl+S)"""
        try:
            cmds.file(save=True)
            print("Scene saved successfully")
            return True
        except Exception as e:
            print("Failed to save scene: {}".format(e))
            return False


class NonManifoldCheck(SanityCheck):
    """Check for non-manifold geometry in export groups"""
    
    def __init__(self):
        super(NonManifoldCheck, self).__init__(
            "Non-Manifold Geometry",
            "Export groups must not contain non-manifold geometry"
        )
        self.output_groups = []
        self.can_fix = False  # No auto-fix for non-manifold
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check for non-manifold geometry in all meshes under output groups"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            return self.status, self.message
        
        non_manifold_meshes = []
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all mesh shapes under this group (including hierarchy)
            all_descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='mesh') or []
            
            for mesh_shape in all_descendants:
                # Check for non-manifold geometry
                non_manifold_verts = cmds.polyInfo(mesh_shape, nonManifoldVertices=True) or []
                non_manifold_edges = cmds.polyInfo(mesh_shape, nonManifoldEdges=True) or []
                
                if non_manifold_verts or non_manifold_edges:
                    # Get transform name for cleaner display
                    transform = cmds.listRelatives(mesh_shape, parent=True, fullPath=True)
                    if transform:
                        mesh_name = transform[0].split('|')[-1]  # Get short name
                    else:
                        mesh_name = mesh_shape.split('|')[-1]
                    
                    non_manifold_meshes.append(mesh_name)
        
        # Check results
        if non_manifold_meshes:
            self.status = SanityCheckStatus.FAIL
            if len(non_manifold_meshes) == 1:
                self.message = "Non-manifold found: {}".format(non_manifold_meshes[0])
            else:
                self.message = "Non-manifold found in {} meshes".format(len(non_manifold_meshes))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No non-manifold geometry found"
        return self.status, self.message


class NamespacesCheck(SanityCheck):
    """Check for unwanted namespaces in the scene"""
    
    def __init__(self):
        super(NamespacesCheck, self).__init__(
            "Namespaces",
            "Scene should not contain custom namespaces"
        )
        self.can_fix = True
    
    def run(self):
        """Check for namespaces other than default Maya namespaces"""
        # Get all namespaces
        all_namespaces = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or []
        
        # Filter out default Maya namespaces
        default_namespaces = ['UI', 'shared']
        custom_namespaces = [ns for ns in all_namespaces if ns not in default_namespaces]
        
        if custom_namespaces:
            self.status = SanityCheckStatus.FAIL
            if len(custom_namespaces) == 1:
                self.message = "Namespace found: {}".format(custom_namespaces[0])
            else:
                self.message = "{} namespaces found".format(len(custom_namespaces))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No custom namespaces"
        return self.status, self.message
    
    def fix(self):
        """Delete all custom namespaces by merging with root"""
        try:
            all_namespaces = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or []
            default_namespaces = ['UI', 'shared']
            custom_namespaces = [ns for ns in all_namespaces if ns not in default_namespaces]
            
            # Remove namespaces from deepest to shallowest
            custom_namespaces.sort(key=lambda x: x.count(':'), reverse=True)
            
            for ns in custom_namespaces:
                if cmds.namespace(exists=ns):
                    cmds.namespace(removeNamespace=ns, mergeNamespaceWithRoot=True)
                    print("Removed namespace: {}".format(ns))
            
            print("All custom namespaces removed")
            return True
        except Exception as e:
            print("Failed to remove namespaces: {}".format(e))
            return False


class FpsCheck(SanityCheck):
    """Check if frame rate is set to 24 fps"""
    
    def __init__(self):
        super(FpsCheck, self).__init__(
            "FPS",
            "Frame rate must be set to 24 fps"
        )
        self.can_fix = True
    
    def run(self):
        """Check if current frame rate is 24 fps"""
        current_unit = cmds.currentUnit(query=True, time=True)
        
        # Maya time unit strings for 24 fps
        valid_24fps = ['film', '24fps']
        
        if current_unit not in valid_24fps:
            self.status = SanityCheckStatus.FAIL
            self.message = "FPS is {} (should be 24fps)".format(current_unit)
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "FPS set to 24"
        return self.status, self.message
    
    def fix(self):
        """Set frame rate to 24 fps"""
        try:
            cmds.currentUnit(time='film')  # film = 24fps
            print("Frame rate set to 24 fps")
            return True
        except Exception as e:
            print("Failed to set frame rate: {}".format(e))
            return False


class ConstructionHistoryCheck(SanityCheck):
    """Check for construction history on geometry in export groups"""
    
    def __init__(self):
        super(ConstructionHistoryCheck, self).__init__(
            "Construction History",
            "Geometry must not have construction history"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check for construction history on all transforms under output groups"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        objects_with_history = []
        self.details = []  # Clear previous details
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all transforms under this group (including the group itself and all descendants)
            all_transforms = [group]
            descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
            all_transforms.extend(descendants)
            
            for transform in all_transforms:
                # Check if transform has construction history
                history = cmds.listHistory(transform, pruneDagObjects=True) or []
                
                # Filter out shape nodes and normal nodes - we only care about construction nodes
                construction_nodes = []
                
                # Node types to IGNORE (these are normal, not construction history)
                ignore_types = [
                    'mesh', 'nurbsCurve', 'nurbsSurface', 'transform',  # Geometry and transforms
                    'groupId', 'groupParts',  # Normal grouping nodes
                    'shadingEngine', 'materialInfo',  # Shading nodes
                    'lambert', 'phong', 'blinn', 'standardSurface',  # Shader nodes
                    'file', 'place2dTexture',  # Texture nodes
                    'initialShadingGroup'  # Default shading
                ]
                
                for node in history:
                    node_type = cmds.nodeType(node)
                    
                    # Skip ignored types
                    if node_type in ignore_types:
                        continue
                    
                    # Skip if it's a shader/texture (check inheritance)
                    if cmds.nodeType(node, inherited=True, isTypeName='shader'):
                        continue
                    if cmds.nodeType(node, inherited=True, isTypeName='texture'):
                        continue
                    
                    # This is actual construction history
                    construction_nodes.append(node)
                
                if construction_nodes:
                    obj_name = transform.split('|')[-1]  # Get short name
                    objects_with_history.append(obj_name)
                    
                    # Store detailed info with node types for debugging
                    node_types = list(set([cmds.nodeType(n) for n in construction_nodes]))
                    self.details.append("Construction history on {}: {}".format(
                        obj_name, ", ".join(node_types)))
        
        # Check results
        if objects_with_history:
            self.status = SanityCheckStatus.FAIL
            if len(objects_with_history) == 1:
                self.message = "History found: {}".format(objects_with_history[0])
            else:
                self.message = "History found on {} objects".format(len(objects_with_history))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No construction history"
        self.details = []
        return self.status, self.message
    
    def fix(self):
        """Delete construction history on all objects in output groups"""
        try:
            if not self.output_groups:
                return False
            
            objects_to_clean = []
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all transforms
                all_transforms = [group]
                descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
                all_transforms.extend(descendants)
                objects_to_clean.extend(all_transforms)
            
            if not objects_to_clean:
                return False
            
            # Delete history
            for obj in objects_to_clean:
                if cmds.objExists(obj):
                    cmds.delete(obj, constructionHistory=True)
            
            print("Construction history deleted")
            return True
        except Exception as e:
            print("Failed to delete construction history: {}".format(e))
            return False


class TransformCheck(SanityCheck):
    """Check for non-zeroed transforms on geometry in export groups"""
    
    def __init__(self):
        super(TransformCheck, self).__init__(
            "Transform",
            "Transforms must be frozen (zeroed out)"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check for non-default transforms on all transforms under output groups"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        objects_with_transforms = []
        self.details = []  # Clear previous details
        tolerance = 0.0001  # Small tolerance for floating point comparison
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all transforms under this group (including the group itself and all descendants)
            all_transforms = [group]
            descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
            all_transforms.extend(descendants)
            
            for transform in all_transforms:
                # Get transform attributes
                translate = cmds.getAttr('{}.translate'.format(transform))[0]
                rotate = cmds.getAttr('{}.rotate'.format(transform))[0]
                scale = cmds.getAttr('{}.scale'.format(transform))[0]
                
                # Check if transforms are non-default
                has_translation = any(abs(v) > tolerance for v in translate)
                has_rotation = any(abs(v) > tolerance for v in rotate)
                has_non_uniform_scale = any(abs(v - 1.0) > tolerance for v in scale)
                
                if has_translation or has_rotation or has_non_uniform_scale:
                    obj_name = transform.split('|')[-1]  # Get short name
                    objects_with_transforms.append(obj_name)
                    self.details.append("Non-frozen transform: {}".format(obj_name))
        
        # Check results
        if objects_with_transforms:
            self.status = SanityCheckStatus.FAIL
            if len(objects_with_transforms) == 1:
                self.message = "Non-frozen transform: {}".format(objects_with_transforms[0])
            else:
                self.message = "Non-frozen transforms on {} objects".format(len(objects_with_transforms))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "All transforms frozen"
        self.details = []
        return self.status, self.message
    
    def fix(self):
        """Freeze transformations on all objects in output groups"""
        try:
            if not self.output_groups:
                return False
            
            objects_to_freeze = []
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all transforms
                all_transforms = [group]
                descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
                all_transforms.extend(descendants)
                objects_to_freeze.extend(all_transforms)
            
            if not objects_to_freeze:
                return False
            
            # Freeze transformations
            for obj in objects_to_freeze:
                if cmds.objExists(obj):
                    try:
                        cmds.makeIdentity(obj, apply=True, translate=True, rotate=True, scale=True, normal=False)
                    except:
                        # Some objects might not support freeze (like groups with no shape)
                        pass
            
            print("Transforms frozen")
            return True
        except Exception as e:
            print("Failed to freeze transforms: {}".format(e))
            return False


class NgonsCheck(SanityCheck):
    """Check for N-gons (faces with more than 4 sides) in export groups"""
    
    def __init__(self):
        super(NgonsCheck, self).__init__(
            "N-gons",
            "Geometry must not contain N-gons (faces with more than 4 sides)"
        )
        self.output_groups = []
        self.can_fix = False  # No auto-fix for N-gons
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check for N-gons in all meshes under output groups using polyCleanup"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            return self.status, self.message
        
        meshes_with_ngons = []
        
        # Store original selection
        original_selection = cmds.ls(selection=True) or []
        
        try:
            # Check each output group
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Select the group
                cmds.select(group, replace=True)
                
                # Use polyCleanup to select N-gons
                # Parameters: "1","2" = Apply to all + Select matching
                # "0","0","1" = Only check N-gons (5th parameter)
                try:
                    import maya.mel as mel
                    
                    # Disable warnings to avoid "No items found" message
                    cmds.scriptEditorInfo(suppressWarnings=True)
                    
                    # Execute cleanup with correct parameters
                    mel.eval('polyCleanupArgList 4 { "1","2","0","0","1","0","0","0","0","1e-05","0","1e-05","0","1e-05","0","-1","0","0" }')
                    
                    # Re-enable warnings
                    cmds.scriptEditorInfo(suppressWarnings=False)
                    
                    # Check if any faces are now selected (N-gons found)
                    selected_faces = cmds.ls(selection=True, flatten=True) or []
                    selected_faces = [f for f in selected_faces if '.f[' in f]
                    
                    if selected_faces:
                        # Group faces by mesh
                        mesh_ngons = {}
                        for face in selected_faces:
                            # Extract mesh name from face path
                            mesh_path = face.split('.f[')[0]
                            mesh_name = mesh_path.split('|')[-1]
                            
                            if mesh_name not in mesh_ngons:
                                mesh_ngons[mesh_name] = 0
                            mesh_ngons[mesh_name] += 1
                        
                        # Add to results
                        for mesh_name, count in mesh_ngons.items():
                            meshes_with_ngons.append((mesh_name, count))
                
                except Exception as e:
                    # Re-enable warnings in case of error
                    cmds.scriptEditorInfo(suppressWarnings=False)
                    print("Error checking N-gons: {}".format(e))
        
        finally:
            # Restore original selection
            cmds.select(clear=True)
            if original_selection:
                cmds.select(original_selection, replace=True)
        
        # Check results
        self.details = []  # Clear previous details
        if meshes_with_ngons:
            self.status = SanityCheckStatus.FAIL
            # Store detailed info
            for mesh_name, ngon_count in meshes_with_ngons:
                self.details.append("N-gons found in {} ({} faces)".format(mesh_name, ngon_count))
            
            if len(meshes_with_ngons) == 1:
                mesh_name, ngon_count = meshes_with_ngons[0]
                self.message = "N-gons found: {} ({} faces)".format(mesh_name, ngon_count)
            else:
                total_ngons = sum(count for _, count in meshes_with_ngons)
                self.message = "N-gons found in {} meshes ({} faces)".format(
                    len(meshes_with_ngons), total_ngons
                )
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No N-gons found"
        return self.status, self.message


class PivotToOriginCheck(SanityCheck):
    """Check if pivots are at origin (0,0,0)"""
    
    def __init__(self):
        super(PivotToOriginCheck, self).__init__(
            "Pivot To Origin",
            "Pivots must be at world origin (0,0,0)"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check if all pivots are at origin"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        objects_with_bad_pivots = []
        self.details = []  # Clear previous details
        tolerance = 0.0001  # Small tolerance for floating point comparison
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all transforms under this group (including the group itself and all descendants)
            all_transforms = [group]
            descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
            all_transforms.extend(descendants)
            
            for transform in all_transforms:
                # Get rotate and scale pivot positions
                rotate_pivot = cmds.xform(transform, query=True, worldSpace=True, rotatePivot=True)
                scale_pivot = cmds.xform(transform, query=True, worldSpace=True, scalePivot=True)
                
                # Check if pivots are at origin (0,0,0)
                rotate_at_origin = all(abs(v) < tolerance for v in rotate_pivot)
                scale_at_origin = all(abs(v) < tolerance for v in scale_pivot)
                
                if not (rotate_at_origin and scale_at_origin):
                    obj_name = transform.split('|')[-1]  # Get short name
                    objects_with_bad_pivots.append(obj_name)
                    self.details.append("Pivot not at origin: {}".format(obj_name))
        
        # Check results
        if objects_with_bad_pivots:
            self.status = SanityCheckStatus.FAIL
            if len(objects_with_bad_pivots) == 1:
                self.message = "Pivot not at origin: {}".format(objects_with_bad_pivots[0])
            else:
                self.message = "Pivots not at origin on {} objects".format(len(objects_with_bad_pivots))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "All pivots at origin"
        self.details = []
        return self.status, self.message
    
    def fix(self):
        """Move pivots to origin for all objects in output groups"""
        try:
            if not self.output_groups:
                return False
            
            objects_to_fix = []
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all transforms
                all_transforms = [group]
                descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
                all_transforms.extend(descendants)
                objects_to_fix.extend(all_transforms)
            
            if not objects_to_fix:
                return False
            
            # Move pivots to origin for each object
            import maya.mel as mel
            for obj in objects_to_fix:
                if cmds.objExists(obj):
                    # Move rotate and scale pivots to origin
                    cmds.move(0, 0, 0, '{}.scalePivot'.format(obj), '{}.rotatePivot'.format(obj), rpr=True)
            
            # Snap to grid commands
            mel.eval('SnapToGridRelease')
            mel.eval('dR_enterForSnap')
            
            print("Pivots moved to origin")
            return True
        except Exception as e:
            print("Failed to move pivots to origin: {}".format(e))
            import traceback
            traceback.print_exc()
            return False


class GeometryParentsCheck(SanityCheck):
    """Check if geometries are parented to other geometries (should be parented to groups instead)"""
    
    def __init__(self):
        super(GeometryParentsCheck, self).__init__(
            "Geometry Parents",
            "Geometries should not be parented to other geometries"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check if any geometries are parented to other geometries"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        bad_parenting = []
        self.details = []  # Clear previous details
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all mesh shapes under this group
            all_mesh_shapes = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='mesh') or []
            
            for mesh_shape in all_mesh_shapes:
                # Get the transform parent of this mesh
                transform_parent = cmds.listRelatives(mesh_shape, parent=True, fullPath=True)
                if not transform_parent:
                    continue
                
                mesh_transform = transform_parent[0]
                
                # Get the parent of this transform
                parent_of_transform = cmds.listRelatives(mesh_transform, parent=True, fullPath=True)
                if not parent_of_transform:
                    continue
                
                parent_transform = parent_of_transform[0]
                
                # Check if parent has a mesh shape (which means geometry is parented to geometry)
                parent_shapes = cmds.listRelatives(parent_transform, shapes=True, type='mesh') or []
                
                if parent_shapes:
                    # This geometry is parented to another geometry!
                    child_name = mesh_transform.split('|')[-1]
                    parent_name = parent_transform.split('|')[-1]
                    bad_parenting.append((child_name, parent_name))
                    self.details.append("Geo parented to geo: {} -> {}".format(child_name, parent_name))
        
        # Check results
        if bad_parenting:
            self.status = SanityCheckStatus.FAIL
            if len(bad_parenting) == 1:
                child, parent = bad_parenting[0]
                self.message = "Geo parented to geo: {} -> {}".format(child, parent)
            else:
                self.message = "{} geos parented to other geos".format(len(bad_parenting))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No geometry parenting issues"
        self.details = []
        return self.status, self.message
    
    def fix(self):
        """Fix geometry parenting by moving child geometry to same group as parent"""
        try:
            if not self.output_groups:
                return False
            
            fixed_count = 0
            
            # Check each output group
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all mesh shapes
                all_mesh_shapes = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='mesh') or []
                
                for mesh_shape in all_mesh_shapes:
                    transform_parent = cmds.listRelatives(mesh_shape, parent=True, fullPath=True)
                    if not transform_parent:
                        continue
                    
                    mesh_transform = transform_parent[0]
                    parent_of_transform = cmds.listRelatives(mesh_transform, parent=True, fullPath=True)
                    if not parent_of_transform:
                        continue
                    
                    parent_transform = parent_of_transform[0]
                    parent_shapes = cmds.listRelatives(parent_transform, shapes=True, type='mesh') or []
                    
                    if parent_shapes:
                        # Found geometry parented to geometry
                        # Get the parent of the parent (the group)
                        grandparent = cmds.listRelatives(parent_transform, parent=True, fullPath=True)
                        
                        if grandparent:
                            # Parent the child mesh to the same group as its parent
                            cmds.parent(mesh_transform, grandparent[0])
                            print("Reparented {} to {}".format(
                                mesh_transform.split('|')[-1],
                                grandparent[0].split('|')[-1]
                            ))
                            fixed_count += 1
            
            if fixed_count > 0:
                print("Fixed {} geometry parenting issues".format(fixed_count))
                return True
            else:
                return False
                
        except Exception as e:
            print("Failed to fix geometry parenting: {}".format(e))
            import traceback
            traceback.print_exc()
            return False


class LockedAttributesCheck(SanityCheck):
    """Check for locked attributes on transforms"""
    
    def __init__(self):
        super(LockedAttributesCheck, self).__init__(
            "Locked Attributes",
            "Transform attributes should not be locked"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check for locked attributes on all transforms"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        objects_with_locked_attrs = []
        self.details = []  # Clear previous details
        
        # Common transform attributes to check
        attrs_to_check = [
            'tx', 'ty', 'tz',           # translate
            'rx', 'ry', 'rz',           # rotate
            'sx', 'sy', 'sz',           # scale
            'v'                          # visibility
        ]
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all transforms under this group (including the group itself and all descendants)
            all_transforms = [group]
            descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
            all_transforms.extend(descendants)
            
            for transform in all_transforms:
                locked_attrs = []
                
                # Check each attribute
                for attr in attrs_to_check:
                    attr_name = '{}.{}'.format(transform, attr)
                    if cmds.objExists(attr_name):
                        if cmds.getAttr(attr_name, lock=True):
                            locked_attrs.append(attr)
                
                if locked_attrs:
                    obj_name = transform.split('|')[-1]  # Get short name
                    objects_with_locked_attrs.append(obj_name)
                    # Store detailed info with locked attributes
                    attrs_str = ", ".join(locked_attrs)
                    self.details.append("Locked attributes on {}: {}".format(obj_name, attrs_str))
        
        # Check results
        if objects_with_locked_attrs:
            self.status = SanityCheckStatus.FAIL
            if len(objects_with_locked_attrs) == 1:
                self.message = "Locked attributes: {}".format(objects_with_locked_attrs[0])
            else:
                self.message = "Locked attributes on {} objects".format(len(objects_with_locked_attrs))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No locked attributes"
        self.details = []
        return self.status, self.message
    
    def fix(self):
        """Unlock all locked attributes"""
        try:
            if not self.output_groups:
                return False
            
            fixed_count = 0
            
            # Common transform attributes to unlock
            attrs_to_unlock = [
                'tx', 'ty', 'tz',
                'rx', 'ry', 'rz',
                'sx', 'sy', 'sz',
                'v'
            ]
            
            # Check each output group
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all transforms
                all_transforms = [group]
                descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
                all_transforms.extend(descendants)
                
                for transform in all_transforms:
                    for attr in attrs_to_unlock:
                        attr_name = '{}.{}'.format(transform, attr)
                        if cmds.objExists(attr_name):
                            if cmds.getAttr(attr_name, lock=True):
                                # Unlock the attribute using MEL command
                                import maya.mel as mel
                                mel.eval('CBunlockAttr "{}"'.format(attr_name))
                                fixed_count += 1
            
            if fixed_count > 0:
                print("Unlocked {} attributes".format(fixed_count))
                return True
            else:
                return False
                
        except Exception as e:
            print("Failed to unlock attributes: {}".format(e))
            import traceback
            traceback.print_exc()
            return False


class EmptyGroupsCheck(SanityCheck):
    """Check for empty groups (transforms with no children)"""
    
    def __init__(self):
        super(EmptyGroupsCheck, self).__init__(
            "Empty Groups",
            "Empty groups should be removed"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check for empty groups"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            return self.status, self.message
        
        empty_groups = []
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all transforms under this group (excluding the output group itself)
            descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
            
            for transform in descendants:
                # Check if this transform has no children (no shapes, no child transforms)
                children = cmds.listRelatives(transform, children=True, fullPath=True) or []
                
                if not children:
                    # This is an empty group
                    obj_name = transform.split('|')[-1]  # Get short name
                    empty_groups.append(obj_name)
        
        # Check results
        if empty_groups:
            self.status = SanityCheckStatus.FAIL
            if len(empty_groups) == 1:
                self.message = "Empty group: {}".format(empty_groups[0])
            else:
                self.message = "{} empty groups found".format(len(empty_groups))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No empty groups"
        return self.status, self.message
    
    def fix(self):
        """Delete all empty groups"""
        try:
            if not self.output_groups:
                return False
            
            deleted_count = 0
            
            # Check each output group
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all transforms (we need to check multiple times as deleting creates new empty groups)
                # Loop until no more empty groups are found
                while True:
                    descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
                    
                    empty_found = False
                    for transform in descendants:
                        # Check if empty
                        children = cmds.listRelatives(transform, children=True, fullPath=True) or []
                        
                        if not children:
                            # Delete empty group
                            try:
                                cmds.delete(transform)
                                print("Deleted empty group: {}".format(transform.split('|')[-1]))
                                deleted_count += 1
                                empty_found = True
                            except:
                                pass
                    
                    # If no empty groups found in this pass, we're done
                    if not empty_found:
                        break
            
            if deleted_count > 0:
                print("Deleted {} empty groups".format(deleted_count))
                return True
            else:
                return False
                
        except Exception as e:
            print("Failed to delete empty groups: {}".format(e))
            import traceback
            traceback.print_exc()
            return False


class KeyframesCheck(SanityCheck):
    """Check if any objects have keyframes (animation)"""
    
    def __init__(self):
        super(KeyframesCheck, self).__init__(
            "Keyframes",
            "Objects should not have keyframes (animation)"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check for keyframes on any keyable attributes (optimized)"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        objects_with_keys = []
        self.details = []  # Clear previous details
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all transforms under this group (including the group itself and all descendants)
            all_transforms = [group]
            descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
            all_transforms.extend(descendants)
            
            for transform in all_transforms:
                # OPTIMIZATION: Use listConnections to quickly check for animCurve nodes
                # This is much faster than checking each attribute individually
                anim_curves = cmds.listConnections(transform, source=True, destination=False, 
                                                   type='animCurve') or []
                
                if anim_curves:
                    obj_name = transform.split('|')[-1]  # Get short name
                    key_count = 0
                    
                    # Count total keyframes from all connected animation curves
                    for curve in anim_curves:
                        keys = cmds.keyframe(curve, query=True, keyframeCount=True) or 0
                        key_count += keys
                    
                    objects_with_keys.append(obj_name)
                    self.details.append("Keyframes on {}: {} keys".format(obj_name, key_count))
        
        # Check results
        if objects_with_keys:
            self.status = SanityCheckStatus.FAIL
            if len(objects_with_keys) == 1:
                self.message = "Keyframes found: {}".format(objects_with_keys[0])
            else:
                self.message = "Keyframes found on {} objects".format(len(objects_with_keys))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No keyframes found"
        self.details = []
        return self.status, self.message
    
    def fix(self):
        """Delete all keyframes on objects"""
        try:
            if not self.output_groups:
                return False
            
            deleted_count = 0
            
            # Check each output group
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all transforms
                all_transforms = [group]
                descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
                all_transforms.extend(descendants)
                
                for transform in all_transforms:
                    # Find and delete all animation curves connected to this object
                    anim_curves = cmds.listConnections(transform, source=True, destination=False,
                                                       type='animCurve') or []
                    
                    if anim_curves:
                        # Delete the animation curves
                        for curve in anim_curves:
                            if cmds.objExists(curve):
                                cmds.delete(curve)
                                deleted_count += 1
            
            if deleted_count > 0:
                print("Deleted {} animation curves".format(deleted_count))
                return True
            else:
                return False
                
        except Exception as e:
            print("Failed to delete keyframes: {}".format(e))
            import traceback
            traceback.print_exc()
            return False


class UvsEmptyCheck(SanityCheck):
    """Check if meshes have UV information (informational only, no fix)"""
    
    def __init__(self):
        super(UvsEmptyCheck, self).__init__(
            "Uvs Empty",
            "Check if meshes have UV coordinates"
        )
        self.output_groups = []
        self.can_fix = False  # Informational only
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check if meshes have UVs (optimized)"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        meshes_without_uvs = []
        meshes_with_uvs = 0
        self.details = []  # Clear previous details
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all mesh shapes under this group
            all_mesh_shapes = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='mesh') or []
            
            for mesh_shape in all_mesh_shapes:
                # OPTIMIZATION: Use simple polyEvaluate with uvcoord (fast)
                try:
                    uv_count = cmds.polyEvaluate(mesh_shape, uvcoord=True)
                    has_uvs = uv_count and uv_count > 0
                except:
                    # Fallback: check if UV sets exist and have data
                    uv_sets = cmds.polyUVSet(mesh_shape, query=True, allUVSets=True) or []
                    has_uvs = len(uv_sets) > 0
                
                # Get transform name for display
                transform = cmds.listRelatives(mesh_shape, parent=True, fullPath=True)
                if transform:
                    mesh_name = transform[0].split('|')[-1]
                else:
                    mesh_name = mesh_shape.split('|')[-1]
                
                if has_uvs:
                    meshes_with_uvs += 1
                else:
                    meshes_without_uvs.append(mesh_name)
                    self.details.append("No UVs: {}".format(mesh_name))
        
        # Check results - this is informational, so we use WARNING status instead of FAIL
        total_meshes = meshes_with_uvs + len(meshes_without_uvs)
        
        if meshes_without_uvs:
            self.status = SanityCheckStatus.WARNING
            if len(meshes_without_uvs) == 1:
                self.message = "No UVs: {}".format(meshes_without_uvs[0])
            else:
                self.message = "{}/{} meshes without UVs".format(len(meshes_without_uvs), total_meshes)
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "All meshes have UVs ({})".format(meshes_with_uvs)
        self.details = []
        return self.status, self.message
        return self.status, self.message


class UvsCheck(SanityCheck):
    """Check if UV shells span across multiple UDIMs"""
    
    def __init__(self):
        super(UvsCheck, self).__init__(
            "Uvs Check",
            "UV shells should not span multiple UDIMs"
        )
        self.output_groups = []
        self.can_fix = False  # No automatic fix
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check if UV shells span multiple UDIMs"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        meshes_with_issues = []
        self.details = []  # Clear previous details
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all mesh shapes under this group
            all_mesh_shapes = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='mesh') or []
            
            for mesh_shape in all_mesh_shapes:
                # Get UV sets
                uv_sets = cmds.polyUVSet(mesh_shape, query=True, allUVSets=True) or []
                
                if not uv_sets:
                    continue
                
                # Check each UV set
                for uv_set in uv_sets:
                    try:
                        from maya import OpenMaya as om
                        
                        # Get mesh function set
                        sel_list = om.MSelectionList()
                        sel_list.add(mesh_shape)
                        dag_path = om.MDagPath()
                        sel_list.getDagPath(0, dag_path)
                        mesh_fn = om.MFnMesh(dag_path)
                        
                        # Get UVs
                        u_array = om.MFloatArray()
                        v_array = om.MFloatArray()
                        mesh_fn.getUVs(u_array, v_array, uv_set)
                        
                        if u_array.length() == 0:
                            continue
                        
                        # Get UV shell IDs
                        num_shells = mesh_fn.numUVs(uv_set)
                        if num_shells == 0:
                            continue
                        
                        # Get face-vertex UV assignments
                        uv_counts = om.MIntArray()
                        uv_ids = om.MIntArray()
                        mesh_fn.getAssignedUVs(uv_counts, uv_ids, uv_set)
                        
                        # Group UVs by connectivity (shells)
                        # Build adjacency map
                        face_count = mesh_fn.numPolygons()
                        
                        # OPTIMIZATION: Limit to 500 faces for sampling on heavy meshes
                        max_faces_to_check = min(face_count, 500)
                        
                        # For each face, get its UV indices and check if they span UDIMs
                        shells_spanning_udims = set()
                        
                        uv_id_offset = 0
                        for face_id in range(max_faces_to_check):
                            face_uv_count = uv_counts[face_id]
                            face_uv_indices = []
                            
                            for i in range(face_uv_count):
                                uv_index = uv_ids[uv_id_offset + i]
                                face_uv_indices.append(uv_index)
                            
                            # Check if this face's UVs span multiple UDIMs
                            if face_uv_indices:
                                udims = set()
                                for uv_idx in face_uv_indices:
                                    if uv_idx < u_array.length():
                                        u = u_array[uv_idx]
                                        v = v_array[uv_idx]
                                        
                                        # Calculate UDIM: 1001 + u_tile + (v_tile * 10)
                                        u_tile = int(u)
                                        v_tile = int(v)
                                        udim = 1001 + u_tile + (v_tile * 10)
                                        udims.add(udim)
                                
                                # If face has UVs in multiple UDIMs, flag it
                                if len(udims) > 1:
                                    shells_spanning_udims.add(tuple(sorted(udims)))
                            
                            uv_id_offset += face_uv_count
                        
                        # If we found shells spanning UDIMs, add to issues
                        if shells_spanning_udims:
                            transform = cmds.listRelatives(mesh_shape, parent=True, fullPath=True)
                            if transform:
                                mesh_name = transform[0].split('|')[-1]
                            else:
                                mesh_name = mesh_shape.split('|')[-1]
                            
                            meshes_with_issues.append(mesh_name)
                            
                            # Store detailed info with UDIMs
                            for udim_pair in shells_spanning_udims:
                                udim_str = ", ".join(str(u) for u in udim_pair)
                                self.details.append("UV spans UDIMs in {}: {}".format(mesh_name, udim_str))
                            
                            break  # Found issue, no need to check other UV sets
                    
                    except Exception as e:
                        # If we can't check, skip this mesh
                        print("Error checking UVs for {}: {}".format(mesh_shape, e))
                        continue
        
        # Check results
        if meshes_with_issues:
            self.status = SanityCheckStatus.FAIL
            if len(meshes_with_issues) == 1:
                self.message = "UV spans UDIMs: {}".format(meshes_with_issues[0])
            else:
                self.message = "{} meshes with UVs spanning UDIMs".format(len(meshes_with_issues))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "No UV shells span multiple UDIMs"
        self.details = []
        return self.status, self.message
        return self.status, self.message


class UvSetNameCheck(SanityCheck):
    """Check if meshes have only one UV set named 'map1'"""
    
    def __init__(self):
        super(UvSetNameCheck, self).__init__(
            "Uv Set Name",
            "Meshes should have only one UV set named 'map1'"
        )
        self.output_groups = []
        self.can_fix = False  # No automatic fix
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check if meshes have only 'map1' UV set"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        meshes_with_issues = []
        self.details = []  # Clear previous details
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all mesh shapes under this group
            all_mesh_shapes = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='mesh') or []
            
            for mesh_shape in all_mesh_shapes:
                # Get UV sets
                uv_sets = cmds.polyUVSet(mesh_shape, query=True, allUVSets=True) or []
                
                has_issue = False
                
                # Check if there's exactly one UV set named 'map1'
                if len(uv_sets) != 1:
                    has_issue = True
                elif uv_sets[0] != 'map1':
                    has_issue = True
                
                if has_issue:
                    # Get transform name for display
                    transform = cmds.listRelatives(mesh_shape, parent=True, fullPath=True)
                    if transform:
                        mesh_name = transform[0].split('|')[-1]
                    else:
                        mesh_name = mesh_shape.split('|')[-1]
                    
                    # Create descriptive message
                    if len(uv_sets) == 0:
                        issue_desc = "no UV sets"
                    elif len(uv_sets) > 1:
                        issue_desc = "{} UV sets: {}".format(len(uv_sets), ', '.join(uv_sets))
                    else:
                        issue_desc = "UV set named '{}'".format(uv_sets[0])
                    
                    meshes_with_issues.append((mesh_name, issue_desc))
                    self.details.append("UV set issue on {}: {}".format(mesh_name, issue_desc))
        
        # Check results
        if meshes_with_issues:
            self.status = SanityCheckStatus.FAIL
            if len(meshes_with_issues) == 1:
                mesh_name, issue = meshes_with_issues[0]
                self.message = "UV set issue: {} ({})".format(mesh_name, issue)
            else:
                self.message = "{} meshes with UV set issues".format(len(meshes_with_issues))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "All meshes have 'map1' UV set"
        self.details = []
        return self.status, self.message
        self.status = SanityCheckStatus.PASS
        self.message = "All meshes have 'map1' UV set"
        return self.status, self.message


class UniqueObjectNamesCheck(SanityCheck):
    """Check if all objects have unique names (no duplicates)"""
    
    def __init__(self):
        super(UniqueObjectNamesCheck, self).__init__(
            "Unique Object Names",
            "All objects should have unique names"
        )
        self.output_groups = []
        self.can_fix = True
    
    def set_output_groups(self, groups):
        """Set the output groups to check"""
        self.output_groups = groups if groups else []
    
    def run(self):
        """Check if all object names are unique"""
        if not self.output_groups:
            self.status = SanityCheckStatus.PASS
            self.message = "No output groups to check"
            self.details = []
            return self.status, self.message
        
        duplicate_names = []
        self.details = []  # Clear previous details
        
        # Check each output group
        for group in self.output_groups:
            if not cmds.objExists(group):
                continue
            
            # Get all transforms under this group (including the group itself and all descendants)
            all_transforms = [group]
            descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
            all_transforms.extend(descendants)
            
            # Count short names
            name_counts = {}
            for transform in all_transforms:
                short_name = transform.split('|')[-1]
                if short_name not in name_counts:
                    name_counts[short_name] = []
                name_counts[short_name].append(transform)
            
            # Find duplicates (names that appear more than once)
            for name, paths in name_counts.items():
                if len(paths) > 1:
                    duplicate_names.append(name)
                    self.details.append("Duplicate name '{}' ({} occurrences)".format(name, len(paths)))
        
        # Check results
        if duplicate_names:
            self.status = SanityCheckStatus.FAIL
            if len(duplicate_names) == 1:
                self.message = "Duplicate name: {}".format(duplicate_names[0])
            else:
                self.message = "{} duplicate names found".format(len(duplicate_names))
            return self.status, self.message
        
        self.status = SanityCheckStatus.PASS
        self.message = "All object names are unique"
        self.details = []
        return self.status, self.message
    
    def fix(self):
        """Rename duplicate objects with _01, _02, etc. suffix"""
        try:
            if not self.output_groups:
                return False
            
            renamed_count = 0
            
            # Check each output group
            for group in self.output_groups:
                if not cmds.objExists(group):
                    continue
                
                # Get all transforms
                all_transforms = [group]
                descendants = cmds.listRelatives(group, allDescendents=True, fullPath=True, type='transform') or []
                all_transforms.extend(descendants)
                
                # Count short names and group by name
                name_groups = {}
                for transform in all_transforms:
                    short_name = transform.split('|')[-1]
                    if short_name not in name_groups:
                        name_groups[short_name] = []
                    name_groups[short_name].append(transform)
                
                # Rename duplicates
                for name, paths in name_groups.items():
                    if len(paths) > 1:
                        # Sort by full path for consistent ordering
                        paths.sort()
                        
                        # Keep first one as is, rename others with suffix
                        for i, transform in enumerate(paths):
                            if i > 0:  # Skip first one
                                # Generate new name with suffix
                                suffix_num = i
                                new_name = "{}_{}".format(name, str(suffix_num).zfill(2))
                                
                                # Make sure new name doesn't already exist
                                while cmds.objExists(new_name):
                                    suffix_num += 1
                                    new_name = "{}_{}".format(name, str(suffix_num).zfill(2))
                                
                                # Rename
                                try:
                                    cmds.rename(transform, new_name)
                                    print("Renamed {} to {}".format(name, new_name))
                                    renamed_count += 1
                                except:
                                    print("Warning: Could not rename {}".format(transform))
            
            if renamed_count > 0:
                print("Renamed {} duplicate objects".format(renamed_count))
                return True
            else:
                return False
                
        except Exception as e:
            print("Failed to rename duplicate objects: {}".format(e))
            import traceback
            traceback.print_exc()
            return False


class SanityCheckManager:
    """Manages all sanity checks organized by categories"""
    
    def __init__(self):
        self.categories = {}  # Dict of category_name -> list of checks
        self._mesh_cache = {}  # Cache for mesh shapes to avoid repeated listRelatives
        self._initialize_checks()
    
    def _initialize_checks(self):
        """Initialize all sanity checks organized by categories"""
        # Scene checks
        self.categories['Scene'] = [
            SceneSavedCheck(time_threshold_minutes=15),
            NamespacesCheck(),
            FpsCheck()
        ]
        
        # Modeling checks (in order)
        self.construction_history_check = ConstructionHistoryCheck()
        self.transform_check = TransformCheck()
        self.non_manifold_check = NonManifoldCheck()
        self.ngons_check = NgonsCheck()
        self.pivot_to_origin_check = PivotToOriginCheck()
        self.geometry_parents_check = GeometryParentsCheck()
        self.locked_attributes_check = LockedAttributesCheck()
        self.empty_groups_check = EmptyGroupsCheck()
        self.keyframes_check = KeyframesCheck()
        self.uvs_empty_check = UvsEmptyCheck()
        self.uvs_check = UvsCheck()
        self.uv_set_name_check = UvSetNameCheck()
        self.unique_object_names_check = UniqueObjectNamesCheck()
        
        self.categories['Modeling'] = [
            self.construction_history_check,
            self.transform_check,
            self.non_manifold_check,
            self.ngons_check,
            self.pivot_to_origin_check,
            self.geometry_parents_check,
            self.locked_attributes_check,
            self.empty_groups_check,
            self.keyframes_check,
            self.uvs_empty_check,
            self.uvs_check,
            self.uv_set_name_check,
            self.unique_object_names_check
        ]
    
    def set_output_groups(self, groups):
        """Set output groups for checks that need them"""
        # Clear mesh cache when output groups change
        self._mesh_cache.clear()
        
        self.construction_history_check.set_output_groups(groups)
        self.transform_check.set_output_groups(groups)
        self.non_manifold_check.set_output_groups(groups)
        self.ngons_check.set_output_groups(groups)
        self.pivot_to_origin_check.set_output_groups(groups)
        self.geometry_parents_check.set_output_groups(groups)
        self.locked_attributes_check.set_output_groups(groups)
        self.empty_groups_check.set_output_groups(groups)
        self.keyframes_check.set_output_groups(groups)
        self.uvs_empty_check.set_output_groups(groups)
        self.uvs_check.set_output_groups(groups)
        self.uv_set_name_check.set_output_groups(groups)
        self.unique_object_names_check.set_output_groups(groups)
    
    def run_all_checks(self):
        """Run all checks and return results organized by category"""
        # Clear mesh cache before running checks to ensure fresh data
        self._mesh_cache.clear()
        
        results = {}
        
        for category_name, checks in self.categories.items():
            category_results = []
            for check in checks:
                if check.status != SanityCheckStatus.IGNORED:
                    status, message = check.run()
                    category_results.append({
                        'check': check,
                        'status': status,
                        'message': message
                    })
                else:
                    category_results.append({
                        'check': check,
                        'status': check.status,
                        'message': 'Ignored by user'
                    })
            results[category_name] = category_results
        
        return results
    
    def has_blocking_failures(self):
        """Check if any checks failed (excluding ignored ones)"""
        for category_checks in self.categories.values():
            for check in category_checks:
                if check.status == SanityCheckStatus.FAIL:
                    return True
        return False
    
    def ignore_check(self, check_name):
        """Ignore a specific check by name"""
        for category_checks in self.categories.values():
            for check in category_checks:
                if check.name == check_name:
                    check.ignore()
                    return True
        return False
    
    def reset_check(self, check_name):
        """Reset a specific check by name"""
        for category_checks in self.categories.values():
            for check in category_checks:
                if check.name == check_name:
                    check.reset()
                    return True
        return False


class SanityCheckWidget(QWidget):
    """Widget displaying sanity check results"""
    
    # Signal emitted when checks are updated
    checks_updated = Signal(bool)  # True if all pass, False if any fail
    
    def __init__(self, parent=None):
        super(SanityCheckWidget, self).__init__(parent)
        
        self.manager = SanityCheckManager()
        self.check_items = []  # List of QListWidgetItem for each check
        
        self.create_widgets()
        self.create_layout()
        self.create_connections()
        
        # Run initial check
        self.refresh_checks()
    
    def create_widgets(self):
        """Create UI widgets"""
        # Title
        self.title_label = QLabel("Sanity Check")
        title_font = self.title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(10)
        self.title_label.setFont(title_font)
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setMaximumWidth(80)
        
        # See Details button
        self.details_btn = QPushButton("See Details")
        self.details_btn.setMaximumWidth(100)
        
        # Scene category label
        self.scene_label = QLabel("Scene")
        scene_font = self.scene_label.font()
        scene_font.setBold(True)
        self.scene_label.setFont(scene_font)
        
        # Scene check list
        self.scene_check_list = QListWidget()
        self.scene_check_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.scene_check_list.setMaximumHeight(100)
        self.scene_check_list.setMinimumHeight(60)
        
        # Modeling category label
        self.modeling_label = QLabel("Modeling")
        modeling_font = self.modeling_label.font()
        modeling_font.setBold(True)
        self.modeling_label.setFont(modeling_font)
        
        # Modeling check list (larger height for more checks)
        self.modeling_check_list = QListWidget()
        self.modeling_check_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.modeling_check_list.setMinimumHeight(100)
        
        # Info console (below Modeling list)
        self.info_label = QLabel("Details")
        info_font = self.info_label.font()
        info_font.setBold(True)
        self.info_label.setFont(info_font)
        
        self.info_console = QTextEdit()
        self.info_console.setReadOnly(True)
        self.info_console.setMaximumHeight(80)
        self.info_console.setMinimumHeight(60)
        self.info_console.setPlaceholderText("Select a check to see details...")
        self.info_console.setStyleSheet("QTextEdit { background-color: #2b2b2b; color: #d0d0d0; }")
    
    def create_layout(self):
        """Create layout"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Scene section (fixed height)
        main_layout.addWidget(self.scene_label)
        main_layout.addWidget(self.scene_check_list)

        # Modeling section — expands to fill remaining space
        main_layout.addWidget(self.modeling_label)
        main_layout.addWidget(self.modeling_check_list, 1)

        # Info console (fixed height)
        main_layout.addWidget(self.info_label)
        main_layout.addWidget(self.info_console)

        # Buttons pinned to bottom
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.details_btn)
        button_layout.addWidget(self.refresh_btn)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
    
    def create_connections(self):
        """Create signal connections"""
        self.refresh_btn.clicked.connect(self.refresh_checks)
        self.details_btn.clicked.connect(self.show_details_window)
        self.scene_check_list.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, self.scene_check_list)
        )
        self.modeling_check_list.customContextMenuRequested.connect(
            lambda pos: self.show_context_menu(pos, self.modeling_check_list)
        )
        
        # Connect selection changed to show details
        self.scene_check_list.itemSelectionChanged.connect(self.on_check_selected)
        self.modeling_check_list.itemSelectionChanged.connect(self.on_check_selected)
    
    def on_check_selected(self):
        """Display details when a check is selected"""
        # Find which list has selection
        selected_items = self.scene_check_list.selectedItems()
        if not selected_items:
            selected_items = self.modeling_check_list.selectedItems()
        
        if not selected_items:
            self.info_console.clear()
            return
        
        item = selected_items[0]
        check_name = item.data(Qt.UserRole)
        
        # Find the check in manager
        check_obj = None
        for category_checks in self.manager.categories.values():
            for check in category_checks:
                if check.name == check_name:
                    check_obj = check
                    break
            if check_obj:
                break
        
        if not check_obj:
            self.info_console.clear()
            return
        
        # Display details based on status
        if check_obj.status in [SanityCheckStatus.FAIL, SanityCheckStatus.WARNING]:
            # Get detailed info from the check
            details = self._get_check_details(check_obj)
            self.info_console.setPlainText(details)
        else:
            # For PASS or IGNORED, show simple message
            self.info_console.setPlainText(check_obj.message)
    
    def _get_check_details(self, check):
        """Get detailed information for a check"""
        # Return the check's message which should contain details
        # The message is set by each check's run() method
        return check.message
    
    def refresh_checks(self):
        """Run all checks and update display with progress"""
        # Create progress dialog
        progress = QProgressDialog("Running sanity checks...", None, 0, 100, self)
        progress.setWindowTitle("Sanity Check")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)  # No cancel button
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        
        # Calculate total checks
        total_checks = sum(len(checks) for checks in self.manager.categories.values())
        current_check = 0
        
        # Run checks with progress updates
        results = {}
        for category_name, checks in self.manager.categories.items():
            category_results = []
            for check in checks:
                # Update progress
                current_check += 1
                progress_value = int((current_check / float(total_checks)) * 100)
                progress.setValue(progress_value)
                progress.setLabelText("Checking: {}...".format(check.name))
                QApplication.processEvents()
                
                # Run check
                if check.status != SanityCheckStatus.IGNORED:
                    status, message = check.run()
                    category_results.append({
                        'check': check,
                        'status': status,
                        'message': message
                    })
                else:
                    category_results.append({
                        'check': check,
                        'status': check.status,
                        'message': 'Ignored by user'
                    })
            results[category_name] = category_results
        
        # Update display
        self.update_check_list(results)
        
        # Close progress dialog
        progress.setValue(100)
        progress.close()
        
        # Emit signal with overall status
        has_failures = self.manager.has_blocking_failures()
        self.checks_updated.emit(not has_failures)
    
    def set_output_groups(self, groups):
        """Set output groups for checks that need them"""
        self.manager.set_output_groups(groups)
    
    def _update_single_check_item(self, list_widget, item, check):
        """Update a single check item in the list without refreshing all checks"""
        # Get color based on status
        color = self._get_status_color(check.status)
        
        # Create colored square icon
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, 0, 12, 12)
        painter.end()
        item.setIcon(QIcon(pixmap))
        
        # Update tooltip with message
        if check.status == SanityCheckStatus.IGNORED:
            item.setToolTip("Ignored by user")
        else:
            item.setToolTip(check.message)
    
    def update_check_list(self, results):
        """Update the check lists with results organized by category"""
        # Clear both lists
        self.scene_check_list.clear()
        self.modeling_check_list.clear()
        
        # Populate Scene checks
        if 'Scene' in results:
            for result in results['Scene']:
                self._add_check_item(self.scene_check_list, result)
        
        # Populate Modeling checks
        if 'Modeling' in results:
            for result in results['Modeling']:
                self._add_check_item(self.modeling_check_list, result)
    
    def _add_check_item(self, list_widget, result):
        """Add a check item to a specific list widget"""
        check = result['check']
        status = result['status']
        
        # Simple display: just check name
        item_text = check.name
        item = QListWidgetItem(item_text)
        
        # Set color based on status
        color = self._get_status_color(status)
        
        # Create colored square icon (smaller size)
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, 0, 12, 12)  # Square instead of circle
        painter.end()
        item.setIcon(QIcon(pixmap))
        
        # Store check reference in item
        item.setData(Qt.UserRole, check.name)
        
        # Add tooltip with full message for details
        item.setToolTip("{}: {}".format(check.name, result['message']))
        
        list_widget.addItem(item)
    
    def _get_status_color(self, status):
        """Get color for status"""
        if status == SanityCheckStatus.PASS:
            return QColor(0, 200, 0)  # Green
        elif status == SanityCheckStatus.FAIL:
            return QColor(200, 0, 0)  # Red
        elif status == SanityCheckStatus.IGNORED:
            return QColor(80, 80, 80)  # Dark Gray/Black
        elif status == SanityCheckStatus.WARNING:
            return QColor(255, 165, 0)  # Orange
        else:
            return QColor(128, 128, 128)  # Gray
    
    def show_context_menu(self, position, list_widget):
        """Show context menu for check items"""
        item = list_widget.itemAt(position)
        if not item:
            return
        
        check_name = item.data(Qt.UserRole)
        
        # Find the check
        check = None
        for category_checks in self.manager.categories.values():
            for c in category_checks:
                if c.name == check_name:
                    check = c
                    break
            if check:
                break
        
        if not check:
            return
        
        # Create context menu
        menu = QMenu(self)
        
        # Add Fix option if check can be fixed and has failed
        fix_action = None
        if check.can_fix and check.status == SanityCheckStatus.FAIL:
            fix_action = menu.addAction("Fix")
            menu.addSeparator()
        
        # Add Ignore/Un-ignore option
        ignore_action = None
        reset_action = None
        if check.can_ignore:
            if check.status == SanityCheckStatus.IGNORED:
                reset_action = menu.addAction("Un-ignore")
            else:
                ignore_action = menu.addAction("Ignore")
        
        # Show menu
        if menu.isEmpty():
            return
        
        action = menu.exec_(list_widget.mapToGlobal(position))
        
        if action:
            if action == fix_action:
                # Try to fix the issue
                success = check.fix()
                if success:
                    print("Fixed: {}".format(check.name))
                else:
                    print("Failed to fix: {}".format(check.name))
                
                # Re-run only this specific check instead of all checks
                status, message = check.run()
                
                # Update only this check's item in the list
                self._update_single_check_item(list_widget, item, check)
                
                # Emit signal with overall status
                has_failures = self.manager.has_blocking_failures()
                self.checks_updated.emit(not has_failures)
                
            elif action == reset_action:
                # Reset check
                self.manager.reset_check(check_name)
                # Re-run only this check
                status, message = check.run()
                self._update_single_check_item(list_widget, item, check)
                
                # Emit signal
                has_failures = self.manager.has_blocking_failures()
                self.checks_updated.emit(not has_failures)
                
            elif action == ignore_action:
                # Ignore check
                self.manager.ignore_check(check_name)
                # Update item to show ignored status
                self._update_single_check_item(list_widget, item, check)
                
                # Emit signal
                has_failures = self.manager.has_blocking_failures()
                self.checks_updated.emit(not has_failures)
    
    def get_overall_status(self):
        """Get overall sanity check status"""
        return not self.manager.has_blocking_failures()
    
    def show_details_window(self):
        """Show detailed error report window"""
        details_dialog = SanityCheckDetailsDialog(self.manager, self)
        details_dialog.exec_()


class SanityCheckDetailsDialog(QDialog):
    """Dialog showing detailed sanity check errors"""
    
    def __init__(self, manager, parent=None):
        super(SanityCheckDetailsDialog, self).__init__(parent)
        
        self.manager = manager
        
        self.setWindowTitle("Sanity Check - Detailed Report")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        self.create_widgets()
        self.create_layout()
        self.populate_details()
    
    def create_widgets(self):
        """Create UI widgets"""
        # Title
        self.title_label = QLabel("Detailed Error Report")
        title_font = self.title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(11)
        self.title_label.setFont(title_font)
        
        # Details text area
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setStyleSheet("QTextEdit { background-color: #2b2b2b; color: #d0d0d0; font-family: Consolas, Monaco, monospace; }")
        
        # Close button
        self.close_btn = QPushButton("Close")
        self.close_btn.setMaximumWidth(100)
        self.close_btn.clicked.connect(self.accept)
    
    def create_layout(self):
        """Create layout"""
        main_layout = QVBoxLayout(self)
        
        main_layout.addWidget(self.title_label)
        main_layout.addWidget(self.details_text)
        
        # Button layout
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)
        main_layout.addLayout(button_layout)
    
    def populate_details(self):
        """Populate the details text with all errors"""
        details_lines = []
        
        details_lines.append("=" * 60)
        details_lines.append("SANITY CHECK DETAILED REPORT")
        details_lines.append("=" * 60)
        details_lines.append("")
        
        # Collect all checks with issues
        has_errors = False
        
        for category_name, checks in self.manager.categories.items():
            category_errors = []
            
            for check in checks:
                if check.status in [SanityCheckStatus.FAIL, SanityCheckStatus.WARNING]:
                    has_errors = True
                    
                    # Format status
                    if check.status == SanityCheckStatus.FAIL:
                        status_text = "[FAIL]"
                    else:
                        status_text = "[WARNING]"
                    
                    category_errors.append("  {} {}".format(status_text, check.name))
                    
                    # If check has detailed errors, list them
                    if check.details:
                        for detail in check.details:
                            category_errors.append("    {}".format(detail))
                    else:
                        # Fallback to simple message if no details
                        category_errors.append("    {}".format(check.message))
                    
                    category_errors.append("")
            
            # Add category section if it has errors
            if category_errors:
                details_lines.append("-" * 60)
                details_lines.append("CATEGORY: {}".format(category_name.upper()))
                details_lines.append("-" * 60)
                details_lines.extend(category_errors)
        
        # If no errors, show success message
        if not has_errors:
            details_lines.append("No errors or warnings found!")
            details_lines.append("")
            details_lines.append("All sanity checks passed successfully.")
        
        details_lines.append("")
        details_lines.append("=" * 60)
        details_lines.append("END OF REPORT")
        details_lines.append("=" * 60)
        
        # Set text
        self.details_text.setPlainText("\n".join(details_lines))