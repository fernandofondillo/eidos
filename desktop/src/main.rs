// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use tauri_plugin_shell::ShellExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Lanzar el servidor Python como sidecar
            let shell = app.shell();
            let (mut rx, _child) = shell
                .sidecar("eidos-server")
                .expect("failed to create eidos-server sidecar")
                .args(["web", "--port", "8765"])
                .spawn()
                .expect("failed to spawn eidos-server");

            // Log output del sidecar
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                            println!("[eidos-server] {}", line);
                        }
                        tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                            eprintln!("[eidos-server] {}", line);
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
