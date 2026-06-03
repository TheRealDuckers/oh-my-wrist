// OhMyWristApp.mc — Application entry point for the Oh-My-Wrist widget.
//
// Responsibilities:
//   - Initialise the BLE delegate on app start.
//   - Register the custom BLE GATT profile.
//   - Begin BLE scanning for the desktop daemon.
//   - Return the initial view to the system.
//   - Stop BLE scanning on app exit.

using Toybox.Application;
using Toybox.BluetoothLowEnergy as BLE;
using Toybox.WatchUi;

class OhMyWristApp extends Application.AppBase {
    // Hold a strong reference to the delegate so it is not garbage-collected.
    var bleDelegate;

    // Delay between registerBleProfile() and setScanState(SCANNING).
    // Space BLE ops to avoid back-to-back register/scan calls.
    const START_SCAN_DELAY_MS = 1000;

    function initialize() {
        AppBase.initialize();
    }

    // Called by the system when the widget becomes active.
    function onStart(state) {
        // Initialise the status model with default values.
        StatusModel.initialize();
        ConnectionIdModel.initialize();
        refreshOhmServiceUuid();
        // StatsModel fields are module-level vars; no explicit init needed.

        // Create and register the BLE delegate.
        bleDelegate = new OhMyWristBleDelegate();
        BLE.setDelegate(bleDelegate);

        // Register the custom GATT profile so the watch knows which
        // service / characteristics to look for when scanning.
        try {
            registerBleProfile();
        } catch (ex) {
            System.println(
                "BLE: registerProfile failed: " + ex.getErrorMessage()
            );
            StatusModel.setPhase("error");
            return;
        }

        // Start scanning after a short delay so registerProfile and
        // setScanState are never back-to-back BLE operations.
        // Reuses the delegate's shared _opTimer to stay within device
        // timer-slot limits.
        bleDelegate.scheduleInitialScan(START_SCAN_DELAY_MS);
    }

    // Return the initial view stack: [view, navigation delegate].
    // The delegate enables swipe navigation between Usage (0),
    // History (1, initial), Claude Stats (2), and OpenCode Stats (3).
    // History stays the initial view; swipe/UP reaches Usage, swipe/DOWN
    // reaches the stats screens (which remain last).
    function getInitialView() {
        return [new OhMyWristView(), new OhMyWristDelegate(1)];
    }

    // Called by the system when the widget is closed / times out.
    //
    // Without an explicit unpairDevice() the daemon waits 4–10 s for the BLE
    // supervision timeout to notice the watch left, which blocks the next
    // re-advertise and makes the next widget-open fail. Forcing the link
    // down here lets the daemon's keepalive notice within one tick.
    function onStop(state) {
        if (bleDelegate != null) {
            bleDelegate.cleanup();

            var device = bleDelegate.getConnectedDevice();
            if (device != null) {
                try {
                    BLE.unpairDevice(device);
                } catch (e) {
                    // Best-effort; never block widget close on cleanup.
                }
                return;
            }

            // No live device to unpair: just stop scanning.
            try {
                BLE.setScanState(BLE.SCAN_STATE_OFF);
            } catch (e) {
                System.println("BLE: setScanState(OFF) threw in onStop");
            }
            return;
        }

        // Delegate missing: still attempt to stop scanning safely.
        try {
            BLE.setScanState(BLE.SCAN_STATE_OFF);
        } catch (e) {
            System.println("BLE: setScanState(OFF) threw with null delegate");
        }
    }
}
