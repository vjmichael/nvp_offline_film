import unreal
import json
import math

class NvpEngineBridge:
    def __init__(self):
        # Access the current editor world
        self.editor_subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.world = self.editor_subsystem.get_editor_world()

    def sync_scene_state(self, payload_json_path):
        """
        Reads the VLM inference payload and updates the UE5 scene.
        """
        unreal.log("NVP Bridge: Synchronizing UE5 with VLM Payload...")
        
        with open(payload_json_path, 'r') as file:
            payload = json.load(file)

        dp_config = payload.get("dp_configuration", {})
        acting_params = payload.get("acting_parameters", {})

        if dp_config:
            self._apply_dp_optics(dp_config)
            
        if acting_params:
            self._apply_acting_vectors(acting_params)

        unreal.log("NVP Bridge: Synchronization Complete.")

    def _apply_dp_optics(self, dp_config):
        """
        Maps the Optical Matrix to a UE5 CineCameraActor.
        """
        # Find the active camera (assuming a naming convention for the NVP pipeline)
        camera_name = dp_config.get("camera_id", "NVP_MainCamera")
        camera_actor = self._find_actor_by_name(camera_name)

        if not camera_actor or not isinstance(camera_actor, unreal.CineCameraActor):
            unreal.log_error(f"NVP Bridge: Could not find CineCameraActor named {camera_name}")
            return

        camera_comp = camera_actor.get_cine_camera_component()

        # 1. Apply Transform (Location & Rotation)
        location = dp_config.get("transform", {}).get("location", [0, 0, 0])
        rotation = dp_config.get("transform", {}).get("rotation", [0, 0, 0]) # Pitch, Yaw, Roll
        
        new_transform = unreal.Transform(
            location=unreal.Vector(location[0], location[1], location[2]),
            rotation=unreal.Rotator(rotation[0], rotation[1], rotation[2]).quaternion(),
            scale=unreal.Vector(1, 1, 1)
        )
        camera_actor.set_actor_transform(new_transform, False, False)

        # 2. Apply Lens Settings (Anamorphic, Focal Length, Aperture)
        lens_settings = camera_comp.lens_settings
        lens_settings.min_focal_length = dp_config.get("focal_length", 35.0)
        lens_settings.max_focal_length = dp_config.get("focal_length", 35.0)
        lens_settings.min_f_stop = dp_config.get("aperture", 2.8)
        
        camera_comp.current_focal_length = dp_config.get("focal_length", 35.0)
        camera_comp.current_aperture = dp_config.get("aperture", 2.8)

        # 3. Apply Filmback / Sensor (e.g., Anamorphic format)
        filmback = camera_comp.filmback
        filmback.sensor_width = dp_config.get("sensor_width", 36.0)
        filmback.sensor_height = dp_config.get("sensor_height", 24.0)
        
        unreal.log(f"NVP Bridge: Optical matrix applied to {camera_name}.")

    def _apply_acting_vectors(self, acting_params):
        """
        Maps the Behavioral Matrix to a Character/Metahuman via Sequencer or Control Rig.
        """
        character_name = acting_params.get("character_id", "NVP_LeadActor")
        character_actor = self._find_actor_by_name(character_name)

        if not character_actor:
            unreal.log_warning(f"NVP Bridge: Character {character_name} not found.")
            return

        # Map VLM emotional states to pre-baked Animation Sequences
        # In a highly advanced setup, this would drive Control Rig parameters directly
        stance = acting_params.get("physical_stance", "neutral")
        emotion = acting_params.get("facial_emotion", "neutral")

        unreal.log(f"NVP Bridge: Applying '{stance}' stance and '{emotion}' emotion to {character_name}.")
        
        # Example: Triggering a blueprint custom event that handles the actual animation blending
        # unreal.SystemLibrary.execute_console_command(self.world, f"ce TriggerNVPAnim {character_name} {stance} {emotion}")

    def _find_actor_by_name(self, name):
        """Helper to find an actor in the current level by its string name."""
        actors = unreal.EditorLevelLibrary.get_all_level_actors()
        for actor in actors:
            if actor.get_actor_label() == name:
                return actor
        return None

# Instantiation for the Unreal Python Console
# bridge = NvpEngineBridge()
# bridge.sync_scene_state("C:/NVP_Local_Storage/current_scene_payload.json")