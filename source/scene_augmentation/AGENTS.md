# scene_augmentation

`scene_augmentation` is the simulator-independent scene-bundle augmentation
package. It owns profile validation, object/table discovery, deterministic
sampling, USD/metadata overrides, append/replace allocation, manifests, and
contact-sheet composition.

It must not import `geniesim_benchmark`, launch Isaac Sim, discover benchmark
YAML files, or assume the GenieSim repository layout. Integrations pass an
explicit task directory and consume the returned instance IDs.

Run tests from the repository root:

```bash
PYTHONPATH=source/scene_augmentation/src \
  pytest -q source/scene_augmentation/tests
```
