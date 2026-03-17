mod app;
mod llm;
mod tools;
mod types;
mod views;

use app::App;

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_title("逆星")
            .with_inner_size([900.0, 650.0]),
        ..Default::default()
    };

    eframe::run_native(
        "逆星",
        options,
        Box::new(|cc| Ok(Box::new(App::new(cc)))),
    )
}

