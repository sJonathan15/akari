fn main() {
  // las dos órdenes que puede llamar la página del servicio (ver capabilities/burbujas.json)
  tauri_build::try_build(
    tauri_build::Attributes::new()
      .app_manifest(tauri_build::AppManifest::new().commands(&["burbuja", "alternar_panel"])),
  )
  .expect("tauri-build");
}
