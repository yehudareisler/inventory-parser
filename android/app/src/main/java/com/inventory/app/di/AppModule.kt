package com.inventory.app.di

import android.content.Context
import com.inventory.app.data.ConfigRepository
import com.inventory.app.sheets.AuthManager
import com.inventory.app.sheets.SheetsRepository
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideConfigRepository(
        @ApplicationContext context: Context
    ): ConfigRepository = ConfigRepository(context)

    @Provides
    @Singleton
    fun provideSheetsRepository(): SheetsRepository = SheetsRepository()

    @Provides
    @Singleton
    fun provideAuthManager(
        @ApplicationContext context: Context
    ): AuthManager = AuthManager(context)
}
