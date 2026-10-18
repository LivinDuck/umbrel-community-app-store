class AddBookorbitIdentity < ActiveRecord::Migration[8.0]
  def up
    add_column :books, :bookorbit_id, :string unless column_exists?(:books, :bookorbit_id)
    add_column :books, :bookorbit_metadata, :text unless column_exists?(:books, :bookorbit_metadata)
    unless index_exists?(:books, [:bookorbit_id, :book_type], name: 'index_books_on_bookorbit_and_type')
      add_index :books, [:bookorbit_id, :book_type], unique: true, name: 'index_books_on_bookorbit_and_type'
    end
  end

  def down
    raise ActiveRecord::IrreversibleMigration, 'Retain BookOrbit identity and request metadata'
  end
end
