package com.inventory.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import com.inventory.app.ui.screens.MainScreen
import com.inventory.app.ui.screens.ReviewScreen
import com.inventory.app.ui.screens.SettingsScreen
import com.inventory.app.viewmodel.MainViewModel

sealed class Screen(val route: String) {
    data object Main : Screen("main")
    data object Review : Screen("review")
    data object Settings : Screen("settings")
}

@Composable
fun AppNavigation(
    navController: NavHostController,
    viewModel: MainViewModel,
) {
    NavHost(navController = navController, startDestination = Screen.Main.route) {
        composable(Screen.Main.route) {
            MainScreen(
                viewModel = viewModel,
                onNavigateToReview = { navController.navigate(Screen.Review.route) },
                onNavigateToSettings = { navController.navigate(Screen.Settings.route) },
            )
        }
        composable(Screen.Review.route) {
            ReviewScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
            )
        }
        composable(Screen.Settings.route) {
            SettingsScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
            )
        }
    }
}
