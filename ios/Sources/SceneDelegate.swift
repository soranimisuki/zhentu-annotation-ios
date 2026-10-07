import UIKit

class SceneDelegate: UIResponder, UIWindowSceneDelegate {

    var window: UIWindow?

    func scene(
        _ scene: UIScene,
        willConnectTo session: UISceneSession,
        options connectionOptions: UIScene.ConnectionOptions
    ) {
        guard let windowScene = scene as? UIWindowScene else { return }
        let win = UIWindow(windowScene: windowScene)
        let root = MainViewController()
        win.rootViewController = root
        win.backgroundColor = Self.sandstone
        self.window = win
        win.makeKeyAndVisible()
    }

    static let sandstone = UIColor(red: 0.902, green: 0.882, blue: 0.835, alpha: 1) // #e6e1d5
}
